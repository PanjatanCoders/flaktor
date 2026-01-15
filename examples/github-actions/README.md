# GitHub Actions Integration for Flaktor

This directory contains example GitHub Actions workflows for integrating Flaktor into your CI/CD pipeline.

## Quick Start

1. Copy the workflows from `.github/workflows/` to your repository
2. Adjust the test command for your project
3. Push to GitHub

## Available Workflows

### `flaktor-track.yml` - Track Test Results
Runs on every push and PR to track test results:
- Runs your test suite
- Uploads results to Flaktor
- Checks for flaky tests
- Generates reports as artifacts

### `flaktor-report.yml` - Weekly Reports
Scheduled weekly report that:
- Generates comprehensive flaky test reports
- Creates/updates GitHub Issues for flaky tests
- Helps teams track test health over time

## Setup Instructions

### 1. Add the Workflows

```bash
# From your repository root
mkdir -p .github/workflows
cp examples/github-actions/../.github/workflows/*.yml .github/workflows/
```

### 2. Customize for Your Project

Edit `flaktor-track.yml` and update:

```yaml
# Change the test command
- name: Run tests
  run: |
    pytest \
      --junitxml=test-results/results.xml \
      tests/
```

### 3. Enable Caching

The workflows use GitHub Actions cache to persist the Flaktor database across runs. No additional setup required.

## Workflow Details

### Test Tracking Workflow

```yaml
# Triggers
on:
  push:
    branches: [main, master, develop]
  pull_request:
    branches: [main, master]
```

The workflow:
1. Checks out code
2. Sets up Python environment
3. Installs dependencies
4. Restores Flaktor database from cache
5. Runs tests with JUnit XML output
6. Uploads results to Flaktor
7. Checks for flaky tests
8. Saves database to cache

### Weekly Report Workflow

```yaml
# Triggers
on:
  schedule:
    - cron: '0 9 * * 1'  # Mondays at 9 AM UTC
  workflow_dispatch:     # Manual trigger
```

The workflow:
1. Restores Flaktor database
2. Generates flaky test report
3. Creates/updates GitHub Issue with findings
4. Uploads report as artifact

## Customization Examples

### Different Test Frameworks

**pytest (Python)**:
```yaml
pytest --junitxml=test-results/results.xml tests/
```

**Jest (JavaScript)**:
```yaml
npm test -- --ci --reporters=default --reporters=jest-junit
```

**JUnit (Java/Maven)**:
```yaml
mvn test
# Results in target/surefire-reports/*.xml
```

**Go**:
```yaml
go install github.com/jstemmer/go-junit-report/v2@latest
go test -v ./... 2>&1 | go-junit-report > test-results/results.xml
```

**RSpec (Ruby)**:
```yaml
bundle exec rspec --format RspecJunitFormatter --out test-results/results.xml
```

### Fail on Flaky Tests

Add this step to fail the build when flaky tests are detected:

```yaml
- name: Fail on flaky tests
  run: |
    FLAKY_COUNT=$(flaktor list --flaky --days 7 2>/dev/null | wc -l || echo "0")
    if [ "$FLAKY_COUNT" -gt "1" ]; then
      echo "::error::$FLAKY_COUNT flaky tests detected!"
      exit 1
    fi
```

### Matrix Testing

Track results across multiple Python versions:

```yaml
jobs:
  test:
    strategy:
      matrix:
        python-version: ['3.9', '3.10', '3.11', '3.12']
    steps:
      # ...
      - name: Upload test results to Flaktor
        run: |
          flaktor upload test-results/results.xml \
            --env "python-${{ matrix.python-version }}"
```

### PR Comments

Add flaky test summary as a PR comment:

```yaml
- name: Comment on PR
  if: github.event_name == 'pull_request'
  uses: actions/github-script@v7
  with:
    script: |
      const { execSync } = require('child_process');
      const output = execSync('flaktor list --flaky --days 7').toString();

      await github.rest.issues.createComment({
        issue_number: context.issue.number,
        owner: context.repo.owner,
        repo: context.repo.repo,
        body: `## Flaky Test Summary\n\`\`\`\n${output}\n\`\`\``
      });
```

## Secrets and Permissions

No secrets are required for basic functionality. For creating issues in the weekly report workflow, ensure the workflow has `issues: write` permission:

```yaml
permissions:
  issues: write
  contents: read
```

## Troubleshooting

### Cache Not Persisting
- Ensure the cache key is consistent: `flaktor-db-${{ github.repository }}`
- Check that `.flaktor` directory is in the cache paths

### No Flaky Tests Detected
- Verify tests have run multiple times (minimum 5 runs by default)
- Check the lookback period with `--days` flag
- Ensure timestamps in XML are correct

### Database Not Found
- The database is created on first run
- Check if `flaktor init` ran successfully
- Verify cache restore step completed
