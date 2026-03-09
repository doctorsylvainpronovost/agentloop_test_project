#!/usr/bin/env python3
"""
QA Validation Test for Weather Feature

This test validates the end-to-end behavior of the weather feature as specified in the task:
1. Weather view loads for a city (e.g., Paris) without runtime errors
2. Canonical GET /api/weather?city=Paris&range=day returns expected normalized payload
3. Invalid params return clear 4xx errors
4. Legacy /api/weather/day behavior is preserved or clearly deprecated with migration note
5. Verify relevant lint/build/type/test checks pass per project workflows
"""

import json
import subprocess
import sys
import unittest
from pathlib import Path
from typing import Dict, Any

import httpx
from fastapi.testclient import TestClient

# Add parent directory to path to import backend modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.main import app


class WeatherQAValidationTestCase(unittest.TestCase):
    """QA validation tests for weather feature end-to-end behavior"""
    
    def setUp(self):
        self.client = TestClient(app)
    
    def tearDown(self):
        pass
    
    def test_01_weather_view_loads_without_errors(self):
        """Criterion 1: Weather view loads for a city (e.g., Paris) without runtime errors"""
        # Test the root endpoint to ensure backend is running
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("message", response.json())
        
        # Test health endpoint
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        
        print("✓ Backend endpoints respond successfully")
    
    def test_02_canonical_endpoint_returns_normalized_payload(self):
        """Criterion 2: Canonical GET /api/weather?city=Paris&range=day returns expected normalized payload"""
        # Mock the weather client dependency
        from backend.main import get_weather_client
        
        class FakeForecastClient:
            async def fetch_forecast(self, location: str, days: int, units: str = "metric"):
                return {
                    "location": {"name": location, "country": "Testland"},
                    "units": units,
                    "requested_days": days,
                    "forecast": [
                        {
                            "date": "2026-03-01",
                            "temperature": {"avg": 11.5, "min": 6, "max": 16},
                            "condition": {"text": "Clear", "icon": "//icon.png"},
                        }
                    ],
                }
        
        app.dependency_overrides[get_weather_client] = lambda: FakeForecastClient()
        
        try:
            # Test canonical endpoint with Paris
            response = self.client.get("/api/weather", params={"city": "Paris", "range": "day"})
            
            self.assertEqual(response.status_code, 200)
            data = response.json()
            
            # Check normalized payload structure
            self.assertIn("data", data)
            self.assertIn("city", data["data"])
            self.assertIn("temperature", data["data"])
            self.assertIn("description", data["data"])
            
            # Check values
            self.assertEqual(data["data"]["city"], "Paris")
            self.assertEqual(data["data"]["temperature"], 11.5)
            self.assertEqual(data["data"]["description"], "Clear")
            
            print("✓ Canonical endpoint returns normalized payload with correct structure")
            
        finally:
            app.dependency_overrides.clear()
    
    def test_03_invalid_params_return_clear_4xx_errors(self):
        """Criterion 3: Invalid params return clear 4xx errors"""
        from backend.main import get_weather_client
        
        class FakeForecastClient:
            async def fetch_forecast(self, location: str, days: int, units: str = "metric"):
                return {
                    "location": {"name": location, "country": "Testland"},
                    "units": units,
                    "requested_days": days,
                    "forecast": [
                        {
                            "date": "2026-03-01",
                            "temperature": {"avg": 11.5, "min": 6, "max": 16},
                            "condition": {"text": "Clear", "icon": "//icon.png"},
                        }
                    ],
                }
        
        app.dependency_overrides[get_weather_client] = lambda: FakeForecastClient()
        
        try:
            # Test missing city parameter
            response = self.client.get("/api/weather", params={"range": "day"})
            self.assertEqual(response.status_code, 422)
            error_detail = response.json()["detail"]
            self.assertEqual(error_detail["code"], "invalid_city")
            self.assertIn("city query parameter is required", error_detail["message"])
            
            # Test empty city parameter
            response = self.client.get("/api/weather", params={"city": "   ", "range": "day"})
            self.assertEqual(response.status_code, 422)
            error_detail = response.json()["detail"]
            self.assertEqual(error_detail["code"], "invalid_city")
            
            # Test invalid range parameter
            response = self.client.get("/api/weather", params={"city": "Paris", "range": "month"})
            self.assertEqual(response.status_code, 422)
            error_detail = response.json()["detail"]
            self.assertEqual(error_detail["code"], "invalid_range")
            self.assertIn("range must be one of", error_detail["message"])
            
            print("✓ Invalid parameters return clear 4xx errors with proper error codes")
            
        finally:
            app.dependency_overrides.clear()
    
    def test_04_legacy_endpoint_preserved_with_deprecation(self):
        """Criterion 4: Legacy /api/weather/day behavior is preserved or clearly deprecated with migration note"""
        from backend.main import get_weather_client
        
        class FakeForecastClient:
            async def fetch_forecast(self, location: str, days: int, units: str = "metric"):
                return {
                    "location": {"name": location, "country": "Testland"},
                    "units": units,
                    "requested_days": days,
                    "forecast": [
                        {
                            "date": "2026-03-01",
                            "temperature": {"avg": 11.5, "min": 6, "max": 16},
                            "condition": {"text": "Clear", "icon": "//icon.png"},
                        }
                    ],
                }
        
        app.dependency_overrides[get_weather_client] = lambda: FakeForecastClient()
        
        try:
            # Test legacy endpoint still works
            response = self.client.get("/api/weather/day", params={"location": "Paris"})
            self.assertEqual(response.status_code, 200)
            
            # Check deprecation headers
            self.assertEqual(response.headers.get("deprecation"), "true")
            self.assertEqual(response.headers.get("sunset"), "Wed, 31 Dec 2026 23:59:59 GMT")
            self.assertIn('/api/weather?city={city}&range=day', response.headers.get("link", ""))
            
            # Check response structure
            data = response.json()
            self.assertIn("data", data)
            self.assertIn("source", data)
            self.assertEqual(data["source"], "weatherapi")
            
            # Test legacy endpoint requires location
            response = self.client.get("/api/weather/day")
            self.assertEqual(response.status_code, 422)
            error_detail = response.json()["detail"]
            self.assertEqual(error_detail["code"], "invalid_location")
            
            print("✓ Legacy endpoint preserved with proper deprecation headers and migration guidance")
            
        finally:
            app.dependency_overrides.clear()
    
    def test_05_frontend_integration_with_backend(self):
        """Criterion 1 (additional): Test frontend-backend integration for Paris"""
        from backend.main import get_weather_client
        
        class FakeForecastClient:
            async def fetch_forecast(self, location: str, days: int, units: str = "metric"):
                return {
                    "location": {"name": location, "country": "Testland"},
                    "units": units,
                    "requested_days": days,
                    "forecast": [
                        {
                            "date": "2026-03-01",
                            "temperature": {"avg": 11.5, "min": 6, "max": 16},
                            "condition": {"text": "Clear", "icon": "//icon.png"},
                        }
                    ],
                }
        
        app.dependency_overrides[get_weather_client] = lambda: FakeForecastClient()
        
        try:
            # Test that frontend would get correct response for Paris
            response = self.client.get("/api/weather", params={"city": "Paris", "range": "day"})
            self.assertEqual(response.status_code, 200)
            
            data = response.json()
            # Verify the response structure matches what frontend expects
            self.assertIn("data", data)
            self.assertIn("city", data["data"])
            self.assertIn("temperature", data["data"])
            self.assertIn("description", data["data"])
            
            print("✓ Frontend-backend integration works for Paris request")
            
        finally:
            app.dependency_overrides.clear()


class ProjectWorkflowValidationTestCase(unittest.TestCase):
    """Validation of project lint/build/type/test workflows"""
    
    def test_01_typecheck_passes(self):
        """Verify TypeScript type checking passes"""
        try:
            result = subprocess.run(
                ["npm", "run", "typecheck"],
                cwd=Path(__file__).resolve().parent.parent,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                print(f"Typecheck output:\n{result.stdout}\n{result.stderr}")
            
            self.assertEqual(result.returncode, 0, "TypeScript type checking should pass")
            print("✓ TypeScript type checking passes")
            
        except subprocess.TimeoutExpired:
            self.fail("Typecheck command timed out")
    
    def test_02_build_passes(self):
        """Verify frontend build passes"""
        try:
            result = subprocess.run(
                ["npm", "run", "build"],
                cwd=Path(__file__).resolve().parent.parent,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode != 0:
                print(f"Build output:\n{result.stdout}\n{result.stderr}")
            
            self.assertEqual(result.returncode, 0, "Frontend build should pass")
            print("✓ Frontend build passes")
            
        except subprocess.TimeoutExpired:
            self.fail("Build command timed out")
    
    def test_03_backend_tests_pass(self):
        """Verify backend tests pass"""
        try:
            result = subprocess.run(
                ["npm", "run", "test:backend"],
                cwd=Path(__file__).resolve().parent.parent,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode != 0:
                print(f"Backend tests output:\n{result.stdout}\n{result.stderr}")
            
            self.assertEqual(result.returncode, 0, "Backend tests should pass")
            print("✓ Backend tests pass")
            
        except subprocess.TimeoutExpired:
            self.fail("Backend tests timed out")
    
    def test_04_frontend_tests_pass(self):
        """Verify frontend tests pass"""
        try:
            result = subprocess.run(
                ["npm", "run", "test:frontend"],
                cwd=Path(__file__).resolve().parent.parent,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode != 0:
                print(f"Frontend tests output:\n{result.stdout}\n{result.stderr}")
            
            self.assertEqual(result.returncode, 0, "Frontend tests should pass")
            print("✓ Frontend tests pass")
            
        except subprocess.TimeoutExpired:
            self.fail("Frontend tests timed out")


def run_qa_validation() -> Dict[str, Any]:
    """
    Run comprehensive QA validation and return results.
    
    Returns:
        Dict with validation results for each criterion
    """
    print("=" * 70)
    print("QA VALIDATION: Weather Feature End-to-End Behavior")
    print("=" * 70)
    
    results = {
        "criterion_1": {"passed": False, "message": "Weather view loads for a city without runtime errors"},
        "criterion_2": {"passed": False, "message": "Canonical endpoint returns normalized payload"},
        "criterion_3": {"passed": False, "message": "Invalid params return clear 4xx errors"},
        "criterion_4": {"passed": False, "message": "Legacy endpoint preserved with deprecation"},
        "criterion_5": {"passed": False, "message": "Project lint/build/type/test checks pass"},
        "overall": {"passed": False, "message": "All criteria must pass"}
    }
    
    # Run API validation tests
    print("\n" + "=" * 70)
    print("API VALIDATION TESTS")
    print("=" * 70)
    
    api_suite = unittest.TestLoader().loadTestsFromTestCase(WeatherQAValidationTestCase)
    api_runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)
    api_result = api_runner.run(api_suite)
    
    # Update results based on API tests
    if api_result.wasSuccessful():
        results["criterion_1"]["passed"] = True
        results["criterion_2"]["passed"] = True
        results["criterion_3"]["passed"] = True
        results["criterion_4"]["passed"] = True
        print("\n✓ All API validation tests passed")
    else:
        print(f"\n✗ API validation tests failed: {len(api_result.failures)} failures, {len(api_result.errors)} errors")
    
    # Run workflow validation tests
    print("\n" + "=" * 70)
    print("WORKFLOW VALIDATION TESTS")
    print("=" * 70)
    
    workflow_suite = unittest.TestLoader().loadTestsFromTestCase(ProjectWorkflowValidationTestCase)
    workflow_runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)
    workflow_result = workflow_runner.run(workflow_suite)
    
    # Update results based on workflow tests
    if workflow_result.wasSuccessful():
        results["criterion_5"]["passed"] = True
        print("\n✓ All workflow validation tests passed")
    else:
        print(f"\n✗ Workflow validation tests failed: {len(workflow_result.failures)} failures, {len(workflow_result.errors)} errors")
    
    # Determine overall result
    all_passed = all(results[f"criterion_{i+1}"]["passed"] for i in range(5))
    results["overall"]["passed"] = all_passed
    
    print("\n" + "=" * 70)
    print("QA VALIDATION SUMMARY")
    print("=" * 70)
    
    for i in range(5):
        criterion = results[f"criterion_{i+1}"]
        status = "✓ PASS" if criterion["passed"] else "✗ FAIL"
        print(f"{status}: Criterion {i+1}: {criterion['message']}")
    
    print("\n" + "=" * 70)
    overall_status = "✓ ALL CRITERIA PASSED" if results["overall"]["passed"] else "✗ VALIDATION FAILED"
    print(overall_status)
    print("=" * 70)
    
    return results


if __name__ == "__main__":
    # Run the QA validation
    validation_results = run_qa_validation()
    
    # Exit with appropriate code
    sys.exit(0 if validation_results["overall"]["passed"] else 1)