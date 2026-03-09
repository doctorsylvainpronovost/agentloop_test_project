#!/bin/bash
# QA Validation Script for Weather Feature
# Runs comprehensive validation tests and produces a report

set -e

echo "================================================================"
echo "QA VALIDATION: Weather Feature End-to-End Behavior"
echo "================================================================"
echo "Task: Validate end-to-end behavior of weather feature"
echo "Date: $(date)"
echo "================================================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print status
print_status() {
    local status=$1
    local message=$2
    
    case $status in
        "pass")
            echo -e "${GREEN}✓ PASS${NC}: $message"
            ;;
        "fail")
            echo -e "${RED}✗ FAIL${NC}: $message"
            ;;
        "warn")
            echo -e "${YELLOW}⚠ WARN${NC}: $message"
            ;;
        "info")
            echo -e "${NC}ℹ INFO${NC}: $message"
            ;;
    esac
}

# Function to run command and capture output
run_command() {
    local name=$1
    local cmd=$2
    
    echo ""
    echo "Running: $name"
    echo "Command: $cmd"
    echo "------------------------------------------------"
    
    if eval "$cmd"; then
        print_status "pass" "$name completed successfully"
        return 0
    else
        print_status "fail" "$name failed"
        return 1
    fi
}

# Initialize results
OVERALL_PASS=true
RESULTS=()

# Criterion 1: Weather view loads for a city without runtime errors
echo ""
echo "================================================================"
echo "CRITERION 1: Weather view loads without runtime errors"
echo "================================================================"

# Run frontend validation tests
if run_command "Frontend validation tests" "npm run test:frontend 2>&1"; then
    RESULTS+=("Criterion 1: PASS - Frontend loads without runtime errors")
else
    RESULTS+=("Criterion 1: FAIL - Frontend has runtime errors")
    OVERALL_PASS=false
fi

# Criterion 2: Canonical endpoint returns normalized payload
echo ""
echo "================================================================"
echo "CRITERION 2: Canonical endpoint returns normalized payload"
echo "================================================================"

# Run backend API tests using unittest directly
if run_command "Backend API tests" "cd /Users/sly/GitHub/agentloop_test_project/.worktrees/task-84 && python3 -m unittest tests.qa_weather_validation.WeatherQAValidationTestCase.test_02_canonical_endpoint_returns_normalized_payload -v 2>&1"; then
    RESULTS+=("Criterion 2: PASS - Canonical endpoint returns normalized payload")
else
    RESULTS+=("Criterion 2: FAIL - Canonical endpoint issues")
    OVERALL_PASS=false
fi

# Criterion 3: Invalid params return clear 4xx errors
echo ""
echo "================================================================"
echo "CRITERION 3: Invalid params return clear 4xx errors"
echo "================================================================"

if run_command "Error handling tests" "cd /Users/sly/GitHub/agentloop_test_project/.worktrees/task-84 && python3 -m unittest tests.qa_weather_validation.WeatherQAValidationTestCase.test_03_invalid_params_return_clear_4xx_errors -v 2>&1"; then
    RESULTS+=("Criterion 3: PASS - Invalid params return clear 4xx errors")
else
    RESULTS+=("Criterion 3: FAIL - Error handling issues")
    OVERALL_PASS=false
fi

# Criterion 4: Legacy endpoint preserved with deprecation
echo ""
echo "================================================================"
echo "CRITERION 4: Legacy endpoint preserved with deprecation"
echo "================================================================"

if run_command "Legacy endpoint tests" "cd /Users/sly/GitHub/agentloop_test_project/.worktrees/task-84 && python3 -m unittest tests.qa_weather_validation.WeatherQAValidationTestCase.test_04_legacy_endpoint_preserved_with_deprecation -v 2>&1"; then
    RESULTS+=("Criterion 4: PASS - Legacy endpoint preserved with deprecation")
else
    RESULTS+=("Criterion 4: FAIL - Legacy endpoint issues")
    OVERALL_PASS=false
fi

# Criterion 5: Project lint/build/type/test checks pass
echo ""
echo "================================================================"
echo "CRITERION 5: Project lint/build/type/test checks pass"
echo "================================================================"

# Run type checking
if run_command "TypeScript type checking" "npm run typecheck 2>&1"; then
    TYPE_CHECK_PASS=true
else
    TYPE_CHECK_PASS=false
    OVERALL_PASS=false
fi

# Run build
if run_command "Frontend build" "npm run build 2>&1"; then
    BUILD_PASS=true
else
    BUILD_PASS=false
    OVERALL_PASS=false
fi

# Run backend tests
if run_command "Backend tests" "npm run test:backend 2>&1"; then
    BACKEND_TESTS_PASS=true
else
    BACKEND_TESTS_PASS=false
    OVERALL_PASS=false
fi

# Run frontend tests
if run_command "Frontend tests" "npm run test:frontend 2>&1"; then
    FRONTEND_TESTS_PASS=true
else
    FRONTEND_TESTS_PASS=false
    OVERALL_PASS=false
fi

if $TYPE_CHECK_PASS && $BUILD_PASS && $BACKEND_TESTS_PASS && $FRONTEND_TESTS_PASS; then
    RESULTS+=("Criterion 5: PASS - All project checks pass")
else
    RESULTS+=("Criterion 5: FAIL - Some project checks failed")
fi

# Run comprehensive QA validation test
echo ""
echo "================================================================"
echo "COMPREHENSIVE QA VALIDATION TEST"
echo "================================================================"

if run_command "Comprehensive QA validation" "python3 tests/qa_weather_validation.test.py 2>&1"; then
    COMPREHENSIVE_PASS=true
else
    COMPREHENSIVE_PASS=false
    OVERALL_PASS=false
fi

# Generate final report
echo ""
echo "================================================================"
echo "QA VALIDATION REPORT"
echo "================================================================"
echo "Validation completed at: $(date)"
echo ""

for result in "${RESULTS[@]}"; do
    if [[ $result == *"PASS"* ]]; then
        echo -e "${GREEN}✓${NC} $result"
    else
        echo -e "${RED}✗${NC} $result"
    fi
done

echo ""
echo "================================================================"
if $OVERALL_PASS; then
    echo -e "${GREEN}✅ QA VALIDATION PASSED${NC}"
    echo "All criteria have been successfully validated."
    EXIT_CODE=0
else
    echo -e "${RED}❌ QA VALIDATION FAILED${NC}"
    echo "Some criteria failed validation. See details above."
    EXIT_CODE=1
fi
echo "================================================================"

# Create evidence file
EVIDENCE_FILE="qa_validation_evidence_$(date +%Y%m%d_%H%M%S).txt"
echo ""
echo "Creating evidence file: $EVIDENCE_FILE"
{
    echo "QA Validation Evidence Report"
    echo "============================="
    echo "Date: $(date)"
    echo "Task: Validate end-to-end behavior of weather feature"
    echo ""
    echo "Summary:"
    for result in "${RESULTS[@]}"; do
        echo "  $result"
    done
    echo ""
    echo "Overall Result: $([ $OVERALL_PASS = true ] && echo "PASS" || echo "FAIL")"
} > "$EVIDENCE_FILE"

echo "Evidence saved to $EVIDENCE_FILE"
exit $EXIT_CODE