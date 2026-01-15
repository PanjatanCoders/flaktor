# GitLab CI Integration for Flaktor

This directory contains example GitLab CI/CD configurations for integrating Flaktor into your pipeline.

## Quick Start

1. Copy `.gitlab-ci.yml` to your repository root
2. Adjust the test command for your project
3. Push to GitLab

## Pipeline Stages

### Test Stage
- Runs your test suite with JUnit XML output
- Uploads results to Flaktor
- Stores test results as artifacts

### Analyze Stage
- Checks for flaky tests after each test run
- Can optionally fail the pipeline if flaky tests are detected

### Report Stage (Scheduled)
- Generates weekly reports of test health
- Lists top flaky tests
- Can be triggered manually or on schedule

### Cleanup Stage
- Removes old test data to keep database size manageable
- Runs monthly by default

## Setting Up Scheduled Pipelines

1. Go to **CI/CD > Schedules** in your GitLab project
2. Create a new schedule:
   - **Description**: Weekly Flaktor Report
   - **Interval Pattern**: `0 9 * * 1` (Mondays at 9 AM)
   - **Target Branch**: Your default branch
3. For monthly cleanup, add variable `CLEANUP_ENABLED=true`

## Caching

The pipeline caches:
- pip dependencies (faster installs)
- Flaktor database (persistent tracking across runs)

## Customization

### Fail on Flaky Tests
Uncomment the section in `flaky-check` job to fail the pipeline when flaky tests are detected:

```yaml
- |
  FLAKY_COUNT=$(flaktor list --flaky --days 7 2>/dev/null | grep -c "%" || echo "0")
  if [ "$FLAKY_COUNT" -gt "0" ]; then
    echo "WARNING: $FLAKY_COUNT flaky tests detected!"
    exit 1
  fi
```

### Different Test Frameworks

**pytest (Python)**:
```yaml
pytest --junitxml=test-results/results.xml tests/
```

**Jest (JavaScript)**:
```yaml
jest --ci --reporters=default --reporters=jest-junit
```

**JUnit (Java)**:
```yaml
mvn test -Dsurefire.reportFormat=xml
```

**Go**:
```yaml
go test -v ./... 2>&1 | go-junit-report > test-results/results.xml
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `FLAKTOR_DB` | Database path | `.flaktor/flaktor.db` |
| `CLEANUP_ENABLED` | Enable monthly cleanup | `false` |
