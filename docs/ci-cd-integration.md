# CI/CD Integration Guide

Flaktor is designed to work seamlessly with your CI/CD pipeline. This guide covers integration with popular CI systems.

## Overview

The typical CI/CD integration workflow:

1. **Run tests** with JUnit/xUnit XML output
2. **Upload results** to Flaktor after each test run
3. **Track flakiness** across multiple runs
4. **Generate reports** to identify problematic tests
5. **Clean up** old data periodically

## Supported CI Systems

- [GitHub Actions](#github-actions)
- [GitLab CI/CD](#gitlab-cicd)
- [Jenkins](#jenkins)
- [CircleCI](#circleci)
- [Azure DevOps](#azure-devops)
- [Generic CI](#generic-ci)

---

## GitHub Actions

See [examples/github-actions/](../examples/github-actions/) for complete workflow files.

### Quick Setup

```yaml
# .github/workflows/test.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install flaktor

      - name: Restore Flaktor database
        uses: actions/cache@v4
        with:
          path: .flaktor
          key: flaktor-${{ github.repository }}

      - name: Initialize Flaktor
        run: flaktor init

      - name: Run tests
        run: pytest --junitxml=results.xml tests/
        continue-on-error: true

      - name: Upload to Flaktor
        if: always()
        run: |
          flaktor upload results.xml \
            --branch "${{ github.ref_name }}" \
            --commit "${{ github.sha }}"

      - name: Check flaky tests
        if: always()
        run: flaktor list --flaky --days 7
```

---

## GitLab CI/CD

See [examples/gitlab-ci/](../examples/gitlab-ci/) for complete pipeline configuration.

### Quick Setup

```yaml
# .gitlab-ci.yml
stages:
  - test

variables:
  PIP_CACHE_DIR: "$CI_PROJECT_DIR/.cache/pip"

cache:
  paths:
    - .cache/pip
    - .flaktor/

test:
  stage: test
  image: python:3.11
  script:
    - pip install -r requirements.txt flaktor
    - flaktor init
    - pytest --junitxml=results.xml tests/ || true
    - flaktor upload results.xml --branch "$CI_COMMIT_REF_NAME" --commit "$CI_COMMIT_SHA"
    - flaktor list --flaky --days 7
  artifacts:
    reports:
      junit: results.xml
```

---

## Jenkins

### Pipeline Script

```groovy
pipeline {
    agent any

    stages {
        stage('Setup') {
            steps {
                sh 'pip install flaktor'
                sh 'flaktor init'
            }
        }

        stage('Test') {
            steps {
                sh 'pytest --junitxml=results.xml tests/ || true'
            }
            post {
                always {
                    junit 'results.xml'
                }
            }
        }

        stage('Track') {
            steps {
                sh """
                    flaktor upload results.xml \
                        --branch "${env.GIT_BRANCH}" \
                        --commit "${env.GIT_COMMIT}" \
                        --env "jenkins"
                """
            }
        }

        stage('Report') {
            steps {
                sh 'flaktor list --flaky --days 7'
                sh 'flaktor report --output flaktor-report.txt'
                archiveArtifacts artifacts: 'flaktor-report.txt'
            }
        }
    }
}
```

### Persist Database

Use Jenkins workspace caching or a shared volume to persist the Flaktor database:

```groovy
options {
    // Preserve workspace for database persistence
    skipDefaultCheckout(true)
}
```

Or use a dedicated directory:

```groovy
environment {
    FLAKTOR_DB = '/var/jenkins_home/flaktor/flaktor.db'
}
```

---

## CircleCI

### Configuration

```yaml
# .circleci/config.yml
version: 2.1

jobs:
  test:
    docker:
      - image: cimg/python:3.11
    steps:
      - checkout

      - restore_cache:
          keys:
            - flaktor-db-{{ .Branch }}
            - flaktor-db-

      - run:
          name: Install dependencies
          command: |
            pip install -r requirements.txt
            pip install flaktor

      - run:
          name: Initialize Flaktor
          command: flaktor init

      - run:
          name: Run tests
          command: pytest --junitxml=results.xml tests/ || true

      - run:
          name: Upload to Flaktor
          command: |
            flaktor upload results.xml \
              --branch "$CIRCLE_BRANCH" \
              --commit "$CIRCLE_SHA1"
          when: always

      - run:
          name: Check flaky tests
          command: flaktor list --flaky --days 7
          when: always

      - save_cache:
          key: flaktor-db-{{ .Branch }}-{{ epoch }}
          paths:
            - .flaktor

      - store_test_results:
          path: results.xml

workflows:
  test:
    jobs:
      - test
```

---

## Azure DevOps

### Pipeline YAML

```yaml
# azure-pipelines.yml
trigger:
  - main
  - develop

pool:
  vmImage: 'ubuntu-latest'

variables:
  FLAKTOR_DB: $(Pipeline.Workspace)/.flaktor/flaktor.db

steps:
  - task: UsePythonVersion@0
    inputs:
      versionSpec: '3.11'

  - task: Cache@2
    inputs:
      key: 'flaktor | "$(Agent.OS)"'
      path: $(Pipeline.Workspace)/.flaktor
    displayName: 'Cache Flaktor database'

  - script: |
      pip install -r requirements.txt
      pip install flaktor
    displayName: 'Install dependencies'

  - script: flaktor init
    displayName: 'Initialize Flaktor'

  - script: pytest --junitxml=$(System.DefaultWorkingDirectory)/results.xml tests/
    displayName: 'Run tests'
    continueOnError: true

  - script: |
      flaktor upload results.xml \
        --branch "$(Build.SourceBranchName)" \
        --commit "$(Build.SourceVersion)" \
        --env "azure-devops"
    displayName: 'Upload to Flaktor'
    condition: always()

  - script: flaktor list --flaky --days 7
    displayName: 'Check flaky tests'
    condition: always()

  - task: PublishTestResults@2
    inputs:
      testResultsFormat: 'JUnit'
      testResultsFiles: 'results.xml'
    condition: always()
```

---

## Generic CI

For any CI system, the pattern is:

```bash
# 1. Install Flaktor
pip install flaktor

# 2. Initialize database (first time only)
flaktor init

# 3. Run your tests with JUnit XML output
pytest --junitxml=results.xml tests/
# or: npm test -- --reporters=jest-junit
# or: mvn test
# or: go test -v ./... | go-junit-report > results.xml

# 4. Upload results
flaktor upload results.xml \
  --branch "$BRANCH_NAME" \
  --commit "$COMMIT_SHA" \
  --env "$CI_ENVIRONMENT"

# 5. Check for flaky tests
flaktor list --flaky --days 7

# 6. Generate report (optional)
flaktor report --output report.txt
```

---

## Best Practices

### 1. Persist the Database

The Flaktor database needs to persist across CI runs to track test history. Use your CI's caching mechanism:

- **GitHub Actions**: `actions/cache`
- **GitLab CI**: `cache` directive
- **Jenkins**: Workspace preservation or shared volume
- **CircleCI**: `save_cache`/`restore_cache`

### 2. Always Upload Results

Use `continue-on-error: true` or equivalent to ensure results are uploaded even when tests fail:

```yaml
- name: Run tests
  run: pytest --junitxml=results.xml
  continue-on-error: true

- name: Upload to Flaktor
  if: always()
  run: flaktor upload results.xml
```

### 3. Include Metadata

Always include branch and commit information for better tracking:

```bash
flaktor upload results.xml \
  --branch "$BRANCH" \
  --commit "$COMMIT" \
  --env "$CI_NAME"
```

### 4. Schedule Cleanup

Run periodic cleanup to keep the database size manageable:

```bash
# Weekly or monthly
flaktor clean --days 90 --force
```

### 5. Generate Reports

Create regular reports for team visibility:

```bash
# Weekly scheduled job
flaktor report --days 7 --output weekly-report.txt
```

---

## Troubleshooting

### Database Not Persisting

- Check cache configuration
- Verify cache key is consistent
- Ensure `.flaktor/` directory is included in cache paths

### No Flaky Tests Detected

- Need minimum 5 runs (configurable with `--min-runs`)
- Check lookback period (`--days` flag)
- Verify test timestamps in XML are correct

### Upload Failing

- Ensure database is initialized (`flaktor init`)
- Check XML file path is correct
- Verify XML format is valid JUnit/xUnit

### Large Database

- Run cleanup: `flaktor clean --days 90`
- Reduce lookback period in queries
- Consider separate databases per branch
