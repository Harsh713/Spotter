from datetime import datetime, timedelta, timezone
from unittest import mock
from django.core.cache import cache
from django.test import SimpleTestCase
from rest_framework.test import APISimpleTestCase
from rest_framework import status

from .services.risk_engine import (
    classify_wind_risk,
    classify_rain_risk,
    classify_snow_risk,
    evaluate_checkpoint_risk,
    evaluate_weather_risk
)
from .services.weather_service import (
    extract_weather_at_hour,
    fetch_forecasts,
    grid_key,
    unavailable_weather_point
)
from .services.routing_service import (
    simplify_coordinates,
    get_three_routes,
    _detour_waypoints,
    NoRouteError,
    RoutingServiceError
)
from .services.common import haversine_miles as _haversine
from .services.corridor_service import sample_corridor_points, generate_corridor_heatmap_timeline
from .services.scenario_service import build_storm, simulated_weather
from .services.weather_service import enrich_checkpoints_with_weather
from .serializers import RouteCalculationRequestSerializer
from .services.geocoding_service import geocode_location, _geocode_place
from .services.sampling_service import choose_sampling_interval
from .services.sampling_service import sample_route_checkpoints
from .services.recommendation import rank_routes

class TestRiskEngine(SimpleTestCase):
    """
    Unit tests for Weather Risk Thresholds and Load Weight Escalation Rules.
    Strictly asserts prompt rules.
    """
    def test_wind_base_thresholds(self):
        # <25 mph -> Low
        r, trig, _ = classify_wind_risk(24.0, 20000)
        self.assertEqual(r, "Low")
        self.assertFalse(trig)

        # 25-34 mph -> Moderate
        r, trig, _ = classify_wind_risk(28.0, 20000)
        self.assertEqual(r, "Moderate")
        self.assertFalse(trig)

        # 35-44 mph with load <= 40k -> High
        r, trig, _ = classify_wind_risk(40.0, 35000)
        self.assertEqual(r, "High")
        self.assertFalse(trig)

        # 45-54 mph with load <= 30k -> Severe
        r, trig, _ = classify_wind_risk(50.0, 25000)
        self.assertEqual(r, "Severe")
        self.assertFalse(trig)

    def test_load_rule_ge_55_mph(self):
        # >= 55 mph -> No Travel for ANY load
        for load in [5000, 20000, 35000, 50000, 80000]:
            r, trig, desc = classify_wind_risk(55.0, load)
            self.assertEqual(r, "No Travel", f"Failed for load {load}")
            self.assertTrue(trig)

            r, trig, desc = classify_wind_risk(65.0, load)
            self.assertEqual(r, "No Travel")
            self.assertTrue(trig)

    def test_load_rule_45_54_mph_over_30k(self):
        # 45-54 mph + <= 30,000 lb -> Severe (normal)
        r, trig, _ = classify_wind_risk(48.0, 30000)
        self.assertEqual(r, "Severe")
        self.assertFalse(trig)

        # 45-54 mph + > 30,000 lb -> No Travel (escalated)
        r, trig, desc = classify_wind_risk(48.0, 30001)
        self.assertEqual(r, "No Travel")
        self.assertTrue(trig)
        self.assertIn("escalated from Severe to No Travel", desc)

    def test_load_rule_35_44_mph_over_40k(self):
        # 35-44 mph + <= 40,000 lb -> High (normal)
        r, trig, _ = classify_wind_risk(38.0, 40000)
        self.assertEqual(r, "High")
        self.assertFalse(trig)

        # 35-44 mph + > 40,000 lb -> Severe (escalated)
        r, trig, desc = classify_wind_risk(38.0, 40001)
        self.assertEqual(r, "Severe")
        self.assertTrue(trig)
        self.assertIn("escalated from High to Severe", desc)

    def test_rain_thresholds(self):
        # <0.10: Low, 0.10-0.25: Mod, 0.25-0.50: High, 0.50-1.00: Severe, >1.00: No Travel
        self.assertEqual(classify_rain_risk(0.05), "Low")
        self.assertEqual(classify_rain_risk(0.18), "Moderate")
        self.assertEqual(classify_rain_risk(0.35), "High")
        self.assertEqual(classify_rain_risk(0.85), "Severe")
        self.assertEqual(classify_rain_risk(1.20), "No Travel")

    def test_snow_thresholds(self):
        # <0.5: Low, 0.5-1.0: Mod, 1.0-2.0: High, 2.0-3.0: Severe, >3.0: No Travel
        self.assertEqual(classify_snow_risk(0.2), "Low")
        self.assertEqual(classify_snow_risk(0.7), "Moderate")
        self.assertEqual(classify_snow_risk(1.5), "High")
        self.assertEqual(classify_snow_risk(2.5), "Severe")
        self.assertEqual(classify_snow_risk(3.5), "No Travel")

    def test_exact_boundary_values(self):
        # A value on a shared boundary takes the higher category; the spec's No Travel bounds
        # for rain (> 1.00) and snow (> 3.0) are strict
        for mph, expected in [(24.9, "Low"), (25, "Moderate"), (35, "High"), (45, "Severe"), (55, "No Travel")]:
            self.assertEqual(classify_wind_risk(mph, 10000)[0], expected, mph)
        for rate, expected in [(0.09, "Low"), (0.10, "Moderate"), (0.25, "High"), (0.50, "Severe"),
                               (1.00, "Severe"), (1.01, "No Travel")]:
            self.assertEqual(classify_rain_risk(rate), expected, rate)
        for rate, expected in [(0.49, "Low"), (0.5, "Moderate"), (1.0, "High"), (2.0, "Severe"),
                               (3.0, "Severe"), (3.01, "No Travel")]:
            self.assertEqual(classify_snow_risk(rate), expected, rate)

    def test_combined_weakest_link_evaluation(self):
        # If snow is No Travel, overall must be No Travel even if wind and rain are 0
        eval1 = evaluate_checkpoint_risk(wind_mph=5.0, rain_in_per_hr=0.0, snow_in_per_hr=3.5, load_weight_lbs=20000)
        self.assertEqual(eval1["overall_risk"], "No Travel")
        self.assertEqual(eval1["overall_risk_score"], 5)

        # If wind is escalated to Severe by 45k lb load, overall must be Severe
        eval2 = evaluate_checkpoint_risk(wind_mph=38.0, rain_in_per_hr=0.15, snow_in_per_hr=0.0, load_weight_lbs=45000)
        self.assertEqual(eval2["overall_risk"], "Severe")
        self.assertEqual(eval2["overall_risk_score"], 4)
        self.assertTrue(eval2["load_rule_applied"])

class TestSamplingEngine(SimpleTestCase):
    """
    Unit tests for Checkpoint Discretization and Dynamic ETA calculation.
    """
    def setUp(self):
        # Simulated straight 100-mile highway route from lat 40.0, lon -90.0 to lat 40.0, lon -88.0
        self.coords = [[40.0, -90.0], [40.0, -89.0], [40.0, -88.0]]
        self.total_dist = 100.0
        self.total_dur = 7200  # 2 hours
        self.dep_time = "2026-10-24T08:00:00Z"

    def test_discretization_intervals(self):
        for interval in [10, 25, 50]:
            checkpoints = sample_route_checkpoints(
                coordinates=self.coords,
                total_distance_miles=self.total_dist,
                total_duration_seconds=self.total_dur,
                departure_time=self.dep_time,
                interval_miles=interval
            )
            # Must start at 0.0 and end at 100.0
            self.assertEqual(checkpoints[0]["mile_marker"], 0.0)
            self.assertEqual(checkpoints[-1]["mile_marker"], 100.0)
            # ETAs must be monotonically advancing
            for i in range(1, len(checkpoints)):
                self.assertGreater(checkpoints[i]["elapsed_seconds"], checkpoints[i - 1]["elapsed_seconds"])

class TestRecommendationEngine(SimpleTestCase):
    """
    Unit tests for the 4-Tier Recommendation Hierarchy.
    """
    def test_tier_1_fewest_severe_miles(self):
        r1 = {
            "route": {"route_id": "r1", "name": "Direct Route", "distance_miles": 500, "duration_seconds": 25000},
            "checkpoints": [
                {"mile_marker": 0, "risk": {"overall_risk": "Low", "overall_risk_score": 1}},
                {"mile_marker": 500, "risk": {"overall_risk": "Severe", "overall_risk_score": 4}}
            ]
        }
        r2 = {
            "route": {"route_id": "r2", "name": "Safe Route", "distance_miles": 550, "duration_seconds": 30000},
            "checkpoints": [
                {"mile_marker": 0, "risk": {"overall_risk": "Low", "overall_risk_score": 1}},
                {"mile_marker": 550, "risk": {"overall_risk": "Moderate", "overall_risk_score": 2}}
            ]
        }
        ranked = rank_routes([r1, r2])
        self.assertEqual(ranked[0]["route"]["route_id"], "r2")
        self.assertTrue(ranked[0]["is_recommended"])

    def test_tier_2_fewest_high_miles(self):
        def route(rid, second_risk, second_score, duration):
            return {
                "route": {"route_id": rid, "name": rid, "distance_miles": 500, "duration_seconds": duration},
                "checkpoints": [
                    {"mile_marker": 0, "risk": {"overall_risk": "Low", "overall_risk_score": 1}},
                    {"mile_marker": 500, "risk": {"overall_risk": second_risk, "overall_risk_score": second_score}},
                ]
            }
        ranked = rank_routes([route("windy", "High", 3, 20000), route("calm", "Moderate", 2, 30000)])
        self.assertEqual(ranked[0]["route"]["route_id"], "calm")

    def test_tier_3_lowest_average_risk(self):
        def route(rid, scores, duration):
            return {
                "route": {"route_id": rid, "name": rid, "distance_miles": 300, "duration_seconds": duration},
                "checkpoints": [
                    {"mile_marker": m, "risk": {"overall_risk": ["Low", "Moderate"][s - 1], "overall_risk_score": s}}
                    for m, s in zip((0, 150, 300), scores)
                ]
            }
        ranked = rank_routes([route("mixed", (2, 2, 1), 10000), route("clear", (1, 2, 1), 15000)])
        self.assertEqual(ranked[0]["route"]["route_id"], "clear")

    def test_tier_4_shortest_time_tie_breaker(self):
        r1 = {
            "route": {"route_id": "fast", "name": "Fast Route", "distance_miles": 500, "duration_seconds": 20000},
            "checkpoints": [{"mile_marker": 0, "risk": {"overall_risk": "Low", "overall_risk_score": 1}}]
        }
        r2 = {
            "route": {"route_id": "slow", "name": "Slow Route", "distance_miles": 500, "duration_seconds": 25000},
            "checkpoints": [{"mile_marker": 0, "risk": {"overall_risk": "Low", "overall_risk_score": 1}}]
        }
        ranked = rank_routes([r2, r1])
        self.assertEqual(ranked[0]["route"]["route_id"], "fast")

class TestAPIEndpoints(APISimpleTestCase):
    """
    Unit tests for DRF endpoints.
    """
    def test_health_check(self):
        response = self.client.get('/api/health/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "healthy")

    def test_route_calculation_validation_error(self):
        response = self.client.post('/api/routes/calculate/', data={}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("origin", response.data["errors"])
        self.assertIn("destination", response.data["errors"])

    def test_route_calculation_success(self):
        payload = {
            "origin": "Chicago, IL",
            "destination": "Denver, CO",
            "departure_time": (datetime.now(timezone.utc) + timedelta(hours=1)).strftime("%Y-%m-%dT%H:00:00Z"),
            "load_weight_lbs": 42000,
            "sampling_interval_miles": 50,
            "scenario": "high_wind"
        }
        # Offline: three synthetic road routes stand in for the routing API, and the simulated
        # scenario needs no weather API
        def fake_route(i, bend):
            coords = [[41.0 + bend * min(k, 40 - k) * 0.01, -95.0 + k * 0.25] for k in range(41)]
            return {
                "route_id": f"route_{i}", "name": f"Route {i}", "distance_miles": 530.0 + i * 20,
                "duration_seconds": 30000 + i * 1200, "duration_hours": 8.3 + i * 0.3,
                "coordinates": coords, "segment_durations": None,
            }
        fake = {
            "origin": {"lat": 41.0, "lon": -95.0, "display_name": "Origin", "country_code": "US"},
            "destination": {"lat": 41.0, "lon": -85.0, "display_name": "Destination", "country_code": "US"},
            "routes": [fake_route(1, 0), fake_route(2, 1), fake_route(3, -1)],
        }
        with mock.patch("truck_routing.services.trip_planner.get_three_routes", return_value=fake):
            response = self.client.post('/api/routes/calculate/', data=payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "success")
        self.assertEqual(len(response.data["routes"]), 3)
        self.assertEqual(sum(r["is_recommended"] for r in response.data["routes"]), 1)
        self.assertEqual(response.data["corridor_heatmap"]["hours_count"], 49)
        for route in response.data["routes"]:
            self.assertEqual(route["checkpoints"][0]["mile_marker"], 0.0)
            self.assertEqual(route["checkpoints"][-1]["mile_marker"], route["distance_miles"])


class TestUnavailableWeather(SimpleTestCase):
    """
    Missing forecasts must surface as Unknown and never be scored as Low risk.
    """
    def test_missing_readings_evaluate_to_unknown(self):
        risk = evaluate_weather_risk(unavailable_weather_point(), 42000)
        self.assertEqual(risk["overall_risk"], "Unknown")
        self.assertIsNone(risk["overall_risk_score"])

    def test_eta_outside_forecast_window_is_unavailable(self):
        hourly = {
            "time": ["2026-10-24T08:00", "2026-10-24T09:00"],
            "windspeed_10m": [30.0, 31.0],
            "rain": [0.0, 0.0],
            "snowfall": [0.0, 0.0],
        }
        inside = extract_weather_at_hour(hourly, datetime(2026, 10, 24, 9, 40, tzinfo=timezone.utc))
        self.assertEqual(inside["source"], "open-meteo")
        self.assertEqual(inside["wind_speed_mph"], 31.0)

        outside = extract_weather_at_hour(hourly, datetime(2026, 10, 25, 9, 0, tzinfo=timezone.utc))
        self.assertEqual(outside["source"], "unavailable")
        self.assertIsNone(outside["wind_speed_mph"])

    def test_unknown_miles_excluded_from_average(self):
        route = {
            "route": {"route_id": "r1", "name": "R1", "distance_miles": 100, "duration_seconds": 7200},
            "checkpoints": [
                {"mile_marker": 0, "risk": {"overall_risk": "Moderate", "overall_risk_score": 2}},
                {"mile_marker": 50, "risk": {"overall_risk": "Unknown", "overall_risk_score": None}},
                {"mile_marker": 100, "risk": {"overall_risk": "Moderate", "overall_risk_score": 2}},
            ]
        }
        ranked = rank_routes([route])
        summary = ranked[0]["summary"]
        self.assertEqual(summary["unknown_miles"], 50.0)
        self.assertEqual(summary["average_risk_score"], 2.0)
        self.assertIn("Forecast unavailable for 50.0 mi", ranked[0]["recommendation_reason"])

    def test_route_without_any_forecast_never_beats_known_route(self):
        unknown = {
            "route": {"route_id": "unknown", "name": "U", "distance_miles": 100, "duration_seconds": 3600},
            "checkpoints": [
                {"mile_marker": 0, "risk": {"overall_risk": "Unknown", "overall_risk_score": None}},
                {"mile_marker": 100, "risk": {"overall_risk": "Unknown", "overall_risk_score": None}},
            ]
        }
        known = {
            "route": {"route_id": "known", "name": "K", "distance_miles": 100, "duration_seconds": 7200},
            "checkpoints": [
                {"mile_marker": 0, "risk": {"overall_risk": "Moderate", "overall_risk_score": 2}},
                {"mile_marker": 100, "risk": {"overall_risk": "Moderate", "overall_risk_score": 2}},
            ]
        }
        ranked = rank_routes([unknown, known])
        self.assertEqual(ranked[0]["route"]["route_id"], "known")


class TestBatchedForecasts(SimpleTestCase):
    """
    Forecast fetching dedupes points by grid cell, batches requests and caches results.
    """
    def setUp(self):
        cache.clear()

    def _fake_response(self, n_locations):
        resp = mock.Mock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = [
            {"hourly": {"time": ["2026-10-24T08:00"], "windspeed_10m": [10.0], "rain": [0.0], "snowfall": [0.0]}}
            for _ in range(n_locations)
        ]
        return resp

    def test_dedupes_batches_and_caches(self):
        # 120 distinct grid cells plus near-duplicates that snap to the same cells
        points = [(40.0 + i * 0.1, -90.0) for i in range(120)]
        points += [(lat + 0.01, lon) for lat, lon in points]

        with mock.patch("truck_routing.services.weather_service.requests.get") as get:
            get.side_effect = lambda url, params, **kw: self._fake_response(len(params["latitude"].split(",")))
            results = fetch_forecasts(points)
            self.assertEqual(len(results), 120)
            self.assertEqual(get.call_count, 3)  # ceil(120 / 50)
            self.assertTrue(all(v is not None for v in results.values()))

            fetch_forecasts(points)
            self.assertEqual(get.call_count, 3)  # served from cache

    def test_failed_batch_returns_none_not_fake_weather(self):
        with mock.patch("truck_routing.services.weather_service.time.sleep"), \
                mock.patch("truck_routing.services.weather_service.requests.get", side_effect=ConnectionError("down")) as get:
            results = fetch_forecasts([(41.88, -87.63)])
        self.assertIsNone(results[grid_key(41.88, -87.63)])
        self.assertEqual(get.call_count, 3)  # first try plus two retries

    def test_rate_limited_batch_is_retried(self):
        limited = mock.Mock(status_code=429)
        with mock.patch("truck_routing.services.weather_service.time.sleep"), \
                mock.patch("truck_routing.services.weather_service.requests.get",
                           side_effect=[limited, self._fake_response(1)]) as get:
            results = fetch_forecasts([(41.88, -87.63)])
        self.assertIsNotNone(results[grid_key(41.88, -87.63)])
        self.assertEqual(get.call_count, 2)


class TestPolylineSimplification(SimpleTestCase):
    def test_keeps_endpoints_and_drops_collinear_points(self):
        coords = [[40.0, -90.0 + i * 0.001] for i in range(1001)]
        coords[500] = [40.05, coords[500][1]]  # one real bend
        simplified = simplify_coordinates(coords)
        self.assertEqual(simplified[0], coords[0])
        self.assertEqual(simplified[-1], coords[-1])
        self.assertIn(coords[500], simplified)
        self.assertLess(len(simplified), 10)


class TestWorldwideGeocoding(SimpleTestCase):
    """
    Any place can be geocoded. US matches are preferred unless a foreign match is clearly more
    prominent; whether a road route exists is left to the routing service.
    """
    def setUp(self):
        _geocode_place.cache_clear()
        patcher = mock.patch("truck_routing.services.geocoding_service.time.sleep")
        patcher.start()
        self.addCleanup(patcher.stop)

    @staticmethod
    def _nominatim(results):
        resp = mock.Mock(status_code=200)
        resp.json.return_value = results
        return resp

    @staticmethod
    def _place(name, cc, importance, lat=10.0, lon=20.0):
        return {"lat": str(lat), "lon": str(lon), "display_name": name,
                "importance": importance, "address": {"country_code": cc}}

    def _geocode(self, query, us_results, world_results, photon_features=None):
        responses = [self._nominatim(us_results), self._nominatim(world_results)]
        if photon_features is not None:
            responses.append(self._nominatim({"features": photon_features}))
        with mock.patch("truck_routing.services.geocoding_service.requests.get", side_effect=responses) as get:
            result = geocode_location(query)
        return result, get

    def test_non_us_coordinates_accepted(self):
        loc = geocode_location("34.0837, 74.7973")  # Srinagar
        self.assertAlmostEqual(loc["lat"], 34.0837)

    def test_out_of_range_coordinates_rejected(self):
        with self.assertRaisesRegex(ValueError, "out of range"):
            geocode_location("95.0, 200.0")

    def test_falls_back_to_worldwide_when_no_us_match(self):
        result, get = self._geocode("Srinagar, IN", [], [self._place("Srinagar, India", "in", 0.6)])
        self.assertEqual(result["country_code"], "IN")
        self.assertEqual(get.call_args_list[0].kwargs["params"]["countrycodes"], "us")
        self.assertNotIn("countrycodes", get.call_args_list[1].kwargs["params"])

    def test_much_more_prominent_foreign_place_wins(self):
        result, _ = self._geocode(
            "Toronto",
            [self._place("Toronto, Iowa", "us", 0.46)],
            [self._place("Toronto, Ontario, Canada", "ca", 0.78)],
        )
        self.assertEqual(result["display_name"], "Toronto, Ontario, Canada")

    def test_us_place_kept_when_foreign_match_not_clearly_bigger(self):
        result, _ = self._geocode(
            "Vancouver",
            [self._place("Vancouver, Washington", "us", 0.56)],
            [self._place("Vancouver, British Columbia", "ca", 0.74)],
        )
        self.assertEqual(result["country_code"], "US")

    def test_photon_fallback_prefers_us_candidate(self):
        features = [
            {"geometry": {"coordinates": [86.8, 23.9]}, "properties": {"name": "Somewhere", "countrycode": "IN"}},
            {"geometry": {"coordinates": [-90.0, 40.0]}, "properties": {"name": "Somewhere", "countrycode": "US"}},
        ]
        result, _ = self._geocode("Somewhere", [], [], photon_features=features)
        self.assertEqual(result["country_code"], "US")

    def test_unknown_place_raises(self):
        with self.assertRaisesRegex(ValueError, "Could not find"):
            self._geocode("Qwxzv", [], [], photon_features=[])


class TestLongTripSampling(SimpleTestCase):
    def test_interval_kept_for_us_trips(self):
        self.assertEqual(choose_sampling_interval(10, 1134), 10)  # Chicago to Denver
        self.assertEqual(choose_sampling_interval(10, 2400), 10)  # Seattle to Dallas

    def test_interval_widened_for_very_long_trips(self):
        self.assertEqual(choose_sampling_interval(10, 3000), 25)
        self.assertEqual(choose_sampling_interval(10, 7000), 50)
        self.assertEqual(choose_sampling_interval(25, 20000), 50)  # widest option is the ceiling


def _osrm_route(coords, duration=3600.0, segment_durations=None):
    """Builds a minimal OSRM route object for mocked routing responses."""
    import polyline
    if segment_durations is None:
        segment_durations = [duration / (len(coords) - 1)] * (len(coords) - 1)
    distance_m = sum(
        _haversine(a[0], a[1], b[0], b[1]) for a, b in zip(coords, coords[1:])
    ) / 0.000621371
    return {
        "geometry": polyline.encode(coords),
        "distance": distance_m,
        "duration": duration,
        "legs": [{"annotation": {"duration": segment_durations}}],
    }


def _osrm_response(routes, snap_m=10.0):
    resp = mock.Mock()
    resp.json.return_value = {
        "code": "Ok",
        "routes": routes,
        "waypoints": [{"distance": snap_m}, {"distance": snap_m}],
    }
    return resp


class TestRealRoutesOnly(SimpleTestCase):
    """
    Routes always come from the routing API; duplicates and absurd detours are rejected,
    and nothing is invented when fewer than 3 distinct routes exist.
    """
    ORIGIN, DEST = "41.0, -90.0", "41.0, -88.0"
    DIRECT = [[41.0, -90.0 + i * 0.05] for i in range(41)]
    NORTH = [[41.0 + min(i, 40 - i) * 0.02, -90.0 + i * 0.05] for i in range(41)]

    def setUp(self):
        cache.clear()  # routes are cached per origin/destination

    def test_repeat_trip_reuses_cached_routes(self):
        direct = _osrm_response([_osrm_route(self.DIRECT)])
        duplicate = _osrm_response([_osrm_route(self.DIRECT)])
        with mock.patch("truck_routing.services.routing_service.requests.get",
                        side_effect=[direct] + [duplicate] * 4) as get:
            first = get_three_routes(self.ORIGIN, self.DEST)
            calls_after_first = get.call_count
            second = get_three_routes(self.ORIGIN, self.DEST)
        self.assertEqual(get.call_count, calls_after_first)  # no routing calls on the repeat
        self.assertEqual(first["routes"], second["routes"])

    def test_no_route_raises_instead_of_inventing_one(self):
        resp = mock.Mock()
        resp.json.return_value = {"code": "NoRoute", "routes": []}
        with mock.patch("truck_routing.services.routing_service.requests.get", return_value=resp):
            with self.assertRaisesRegex(NoRouteError, "No drivable road route"):
                get_three_routes(self.ORIGIN, self.DEST)

    def test_far_snap_rejected(self):
        resp = _osrm_response([_osrm_route(self.DIRECT)], snap_m=500000)
        with mock.patch("truck_routing.services.routing_service.requests.get", return_value=resp):
            with self.assertRaisesRegex(NoRouteError, "No drivable road route connects"):
                get_three_routes(self.ORIGIN, self.DEST)

    def test_routing_outage_is_not_reported_as_no_route(self):
        with mock.patch("truck_routing.services.routing_service.requests.get", side_effect=ConnectionError("down")):
            with self.assertRaises(RoutingServiceError):
                get_three_routes(self.ORIGIN, self.DEST)

    def test_duplicates_rejected_and_no_synthetic_fill(self):
        # Direct query: one route. Every detour returns a copy of it, so only 1 distinct route exists.
        direct = _osrm_response([_osrm_route(self.DIRECT)])
        duplicate = _osrm_response([_osrm_route(self.DIRECT)])
        with mock.patch("truck_routing.services.routing_service.requests.get", side_effect=[direct] + [duplicate] * 4):
            result = get_three_routes(self.ORIGIN, self.DEST)
        self.assertEqual(len(result["routes"]), 1)
        self.assertEqual(result["routes"][0]["name"], "Fastest Route")

    def test_distinct_detour_accepted_with_correct_side_label(self):
        direct = _osrm_response([_osrm_route(self.DIRECT)])
        north = _osrm_response([_osrm_route(self.NORTH, duration=4000.0)])
        duplicate = _osrm_response([_osrm_route(self.DIRECT)])
        # Detour order: +0.15 (north), -0.15 (south), +0.3 (north side already found, skipped), -0.3 (south)
        with mock.patch("truck_routing.services.routing_service.requests.get", side_effect=[direct, north, duplicate, duplicate]):
            result = get_three_routes(self.ORIGIN, self.DEST)
        names = [r["name"] for r in result["routes"]]
        self.assertEqual(names, ["Fastest Route", "Northern Alternate"])

    def test_detour_waypoints_scale_with_trip_length(self):
        short = _detour_waypoints(41.0, -90.0, 41.0, -89.0)
        long_ = _detour_waypoints(41.0, -90.0, 41.0, -80.0)
        short_offset = abs(short[0][1][0] - 41.0)
        long_offset = abs(long_[0][1][0] - 41.0)
        self.assertAlmostEqual(long_offset / short_offset, 10.0, places=1)
        self.assertEqual(short[0][0], "Northern")
        self.assertEqual(short[1][0], "Southern")


class TestSegmentDurationETAs(SimpleTestCase):
    def test_eta_follows_per_segment_travel_times(self):
        # 2 equal-length segments: the first takes 3 h (slow), the second 1 h
        coords = [[40.0, -90.0], [40.0, -89.0], [40.0, -88.0]]
        checkpoints = sample_route_checkpoints(
            coordinates=coords,
            total_distance_miles=100.0,
            total_duration_seconds=14400,
            departure_time="2026-10-24T08:00:00Z",
            interval_miles=50,
            segment_durations=[10800, 3600],
        )
        midpoint = next(c for c in checkpoints if c["mile_marker"] == 50.0)
        self.assertEqual(midpoint["elapsed_seconds"], 10800)  # linear model would say 7200
        self.assertEqual(checkpoints[-1]["elapsed_seconds"], 14400)


class TestRainIncludesShowers(SimpleTestCase):
    def test_showers_added_to_rain_rate(self):
        hourly = {
            "time": ["2026-10-24T08:00"],
            "windspeed_10m": [10.0],
            "rain": [0.05],
            "showers": [0.30],
            "snowfall": [0.0],
        }
        weather = extract_weather_at_hour(hourly, datetime(2026, 10, 24, 8, 0, tzinfo=timezone.utc))
        self.assertEqual(weather["rain_in_per_hr"], 0.35)
        self.assertEqual(evaluate_weather_risk(weather, 20000)["rain_risk"], "High")


class TestCorridorStations(SimpleTestCase):
    def test_stations_cover_route_and_merge_overlaps(self):
        route = {"coordinates": [[40.0, -100.0 + i * 0.01] for i in range(1001)]}  # ~530 mi east-west
        stations = sample_corridor_points([route])
        self.assertGreaterEqual(len(stations), 20)  # ~25 mi spacing
        self.assertEqual(sample_corridor_points([route, dict(route)]), stations)  # identical route adds nothing

    def test_station_count_capped_for_long_trips(self):
        route = {"coordinates": [[40.0, -120.0 + i * 0.05] for i in range(1001)]}  # ~2,650 mi
        stations = sample_corridor_points([route], max_points=40)
        self.assertLessEqual(len(stations), 40)

    def test_heatmap_is_columnar_per_metric(self):
        heatmap = generate_corridor_heatmap_timeline(
            [{"lat": 40.0, "lon": -100.0}], "2026-10-24T08:00:00Z", 40000, scenario="high_wind"
        )
        point = heatmap["points"][0]
        for metric in ("wind", "rain", "snow", "risk"):
            self.assertEqual(len(point[metric]), 49)


class TestUnifiedScenarioStorm(SimpleTestCase):
    """
    Demo scenarios use one storm model, so a checkpoint and a heatmap cell at the same place
    and time report identical weather.
    """
    def setUp(self):
        self.departure = datetime(2026, 10, 24, 8, 0, tzinfo=timezone.utc)
        self.storm = build_storm((41.0, -90.0), (41.0, -80.0), self.departure)

    def test_checkpoint_and_heatmap_agree(self):
        lat, lon = 41.0, -85.0  # storm centre (trip midpoint)
        eta = self.departure + timedelta(hours=6)
        checkpoint = {"lat": lat, "lon": lon, "eta_iso": eta.strftime("%Y-%m-%dT%H:%M:%SZ"), "elapsed_seconds": 21600}
        enrich_checkpoints_with_weather([checkpoint], scenario="high_wind", storm=self.storm)

        heatmap = generate_corridor_heatmap_timeline(
            [{"lat": lat, "lon": lon}], self.departure, 42000, scenario="high_wind", storm=self.storm
        )
        self.assertEqual(checkpoint["weather"]["wind_speed_mph"], heatmap["points"][0]["wind"][6])

    def test_storm_strongest_at_centre_and_calm_outside(self):
        at = self.departure + timedelta(hours=12)
        centre = simulated_weather(41.0, -85.0, at, "blizzard", self.storm)
        outside = simulated_weather(41.0, -90.0, at, "blizzard", self.storm)
        self.assertEqual(evaluate_weather_risk(centre, 20000)["overall_risk"], "No Travel")
        self.assertEqual(evaluate_weather_risk(outside, 20000)["overall_risk"], "Low")
        self.assertEqual(centre["source"], "simulated")


class TestDepartureValidation(SimpleTestCase):
    def _errors(self, departure):
        s = RouteCalculationRequestSerializer(data={"origin": "A", "destination": "B", "departure_time": departure})
        s.is_valid()
        return s.errors.get("departure_time")

    def test_within_window_accepted(self):
        self.assertIsNone(self._errors((datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()))

    def test_past_rejected(self):
        self.assertIn("in the past", str(self._errors((datetime.now(timezone.utc) - timedelta(hours=3)).isoformat())))

    def test_beyond_forecast_window_rejected(self):
        self.assertIn("5 days", str(self._errors((datetime.now(timezone.utc) + timedelta(days=6)).isoformat())))

    def test_malformed_rejected(self):
        self.assertIsNotNone(self._errors("next tuesday"))


class TestNoSafeRoute(SimpleTestCase):
    def test_all_routes_no_travel_flagged(self):
        def route(rid, no_travel_end):
            return {
                "route": {"route_id": rid, "name": rid, "distance_miles": 100, "duration_seconds": 3600},
                "checkpoints": [
                    {"mile_marker": 0, "risk": {"overall_risk": "Low", "overall_risk_score": 1}},
                    {"mile_marker": no_travel_end, "risk": {"overall_risk": "No Travel", "overall_risk_score": 5}},
                    {"mile_marker": 100, "risk": {"overall_risk": "Low", "overall_risk_score": 1}},
                ]
            }
        ranked = rank_routes([route("a", 50), route("b", 40)])
        self.assertTrue(ranked[0]["summary"]["has_no_travel"])
        self.assertTrue(ranked[0]["recommendation_reason"].startswith("No safe route"))
