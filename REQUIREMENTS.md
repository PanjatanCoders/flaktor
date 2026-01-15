# Flaktor - Product Requirements Document

> **Flaktor** = Flaky + Detector — An open-source flaky test intelligence tool

---

## 1. Product Overview

**Flaktor** is a framework-agnostic, open-source tool that helps QA and development teams identify, track, and analyze flaky tests in their test suites. It works by analyzing test result files (JUnit XML and other formats) across multiple test runs, detecting patterns, and providing actionable insights.

### Vision
Become the go-to open-source solution for flaky test detection, trusted by QA teams worldwide.

### Tagline
*"Stop guessing. Start knowing why your tests fail."*

---

## 2. Problem Statement

### The Pain
- **Flaky tests waste time**: Engineers spend hours debugging tests that fail randomly
- **CI/CD becomes untrustworthy**: Teams start ignoring failures, assuming they're "just flaky"
- **No visibility**: Teams don't know which tests are flaky until they've wasted significant time
- **Existing solutions are expensive**: Paid tools like Buildkite Test Analytics, Datadog, LaunchDarkly are tied to their ecosystems
- **No root cause analysis**: Knowing a test is flaky isn't enough — teams need to know *why*

### Current Workarounds
- Manual tracking in spreadsheets
- Re-running failed tests blindly
- Disabling flaky tests (hiding the problem)
- Expensive enterprise tools

### Our Solution
A free, self-hosted tool that:
- Automatically detects flaky tests from existing test results
- Provides flakiness scores and trends
- Identifies patterns (time-based, order-based, environment-based)
- Integrates into existing CI/CD workflows with zero code changes

---

## 3. Target Users

### Primary Users
| User | Need |
|------|------|
| **QA Engineers** | Identify which tests to fix first, prove flakiness to developers |
| **SDET / Test Automation Engineers** | Track test suite health, prioritize maintenance |
| **DevOps / Platform Engineers** | Improve CI reliability, reduce build times |

### Secondary Users
| User | Need |
|------|------|
| **Engineering Managers** | Visibility into test suite health metrics |
| **Developers** | Quickly determine if a failure is flaky or real |

### User Environment
- CI/CD systems: GitHub Actions, GitLab CI, Jenkins, CircleCI, Azure DevOps
- Test frameworks: Any framework that outputs JUnit XML (see compatibility list)
- Team size: 5-500 engineers
- Test suite size: 100 - 50,000+ tests

---

## 4. Core Features

### Phase 1: MVP (Foundation)

#### 4.1 Test Result Ingestion
| ID | Requirement |
|----|-------------|
| F1.1 | Parse JUnit XML test result files |
| F1.2 | Support batch upload of multiple XML files |
| F1.3 | Associate results with a "run" (build ID, timestamp, branch, commit) |
| F1.4 | Handle duplicate test names across different classes/files |
| F1.5 | Store historical results in local SQLite database |

#### 4.2 Flakiness Detection
| ID | Requirement |
|----|-------------|
| F2.1 | Calculate flakiness score per test (0-100%) |
| F2.2 | Detect tests with inconsistent results (pass/fail alternation) |
| F2.3 | Configurable lookback window (default: last 30 runs) |
| F2.4 | Minimum run threshold before calculating flakiness (default: 5 runs) |
| F2.5 | Distinguish between flaky, stable-pass, stable-fail, and new tests |

#### 4.3 CLI Interface
| ID | Requirement |
|----|-------------|
| F3.1 | `flaktor upload <path>` - Upload test results |
| F3.2 | `flaktor report` - Generate flakiness report |
| F3.3 | `flaktor list --flaky` - List flaky tests |
| F3.4 | `flaktor history <test-name>` - Show history for specific test |
| F3.5 | `flaktor init` - Initialize database and configuration |
| F3.6 | Output formats: table (default), JSON, CSV |

#### 4.4 Basic Reporting
| ID | Requirement |
|----|-------------|
| F4.1 | Summary: total tests, flaky count, flakiness rate |
| F4.2 | Top 10 flakiest tests with scores |
| F4.3 | Test status distribution (passed, failed, skipped) |
| F4.4 | Trend indicator (getting better/worse) |

---

### Phase 2: Pattern Detection

#### 4.5 Advanced Analysis
| ID | Requirement |
|----|-------------|
| F5.1 | Time-based patterns: fails on specific days/times |
| F5.2 | Order-based patterns: fails when run after specific test |
| F5.3 | Parallel vs serial: fails in parallel, passes in serial |
| F5.4 | Recent regression: started failing after specific date |
| F5.5 | Environment correlation: fails on specific runner/OS |
| F5.6 | Duration anomalies: unusually slow before failing |

#### 4.6 Failure Clustering
| ID | Requirement |
|----|-------------|
| F6.1 | Group tests that fail together |
| F6.2 | Identify common error messages across failures |
| F6.3 | Detect shared root causes |

---

### Phase 3: CI/CD Integration

#### 4.7 GitHub Integration
| ID | Requirement |
|----|-------------|
| F7.1 | GitHub Action for easy integration |
| F7.2 | PR comment with flaky test warnings |
| F7.3 | Status check: warn/fail if flakiness exceeds threshold |
| F7.4 | Link failures to commits/PRs that introduced flakiness |

#### 4.8 Other CI Systems
| ID | Requirement |
|----|-------------|
| F8.1 | GitLab CI template |
| F8.2 | Jenkins plugin or pipeline script |
| F8.3 | Generic webhook for CI notifications |

#### 4.9 Build Intelligence
| ID | Requirement |
|----|-------------|
| F9.1 | Recommend skipping known-flaky tests in PR builds |
| F9.2 | Auto-retry configuration suggestions |
| F9.3 | Quarantine list generation |

---

### Phase 4: Dashboard & Visualization

#### 4.10 Web Dashboard
| ID | Requirement |
|----|-------------|
| F10.1 | Self-hosted HTML dashboard (single file, no server needed) |
| F10.2 | Flakiness trends over time (charts) |
| F10.3 | Test health heatmap |
| F10.4 | Drill-down into individual test history |
| F10.5 | Filter by: branch, date range, flakiness threshold |

#### 4.11 Notifications
| ID | Requirement |
|----|-------------|
| F11.1 | Slack webhook integration |
| F11.2 | Email digest (daily/weekly) |
| F11.3 | Custom webhook for other tools |

---

### Phase 5: Extended Format Support

#### 4.12 Additional Parsers
| ID | Requirement |
|----|-------------|
| F12.1 | Jest JSON output |
| F12.2 | pytest JSON output |
| F12.3 | Allure results |
| F12.4 | TestNG XML (native format) |
| F12.5 | MSTest TRX format |
| F12.6 | Cucumber JSON |
| F12.7 | Generic JSON schema for custom formats |

---

## 5. Technical Requirements

### 5.1 Technology Stack
| Component | Technology | Rationale |
|-----------|------------|-----------|
| Language | Python 3.10+ | Fast development, rich ecosystem, easy for contributors |
| CLI Framework | Typer + Rich | Professional CLI experience with colors and tables |
| Database | SQLite | Zero setup, portable, sufficient for millions of results |
| XML Parsing | lxml | Fast, reliable, handles malformed XML |
| Dashboard | Jinja2 + Chart.js | Static HTML generation, no server needed |
| Packaging | PyPI + Docker | Easy installation, CI-friendly |

### 5.2 Performance Requirements
| ID | Requirement |
|----|-------------|
| P1 | Parse 1000 test results in < 5 seconds |
| P2 | Database queries for 100,000 results in < 1 second |
| P3 | CLI commands respond in < 2 seconds for typical operations |
| P4 | Support up to 1 million historical test results |

### 5.3 Compatibility
| ID | Requirement |
|----|-------------|
| C1 | Run on Linux, macOS, Windows |
| C2 | Python 3.10, 3.11, 3.12 support |
| C3 | Docker image for containerized environments |
| C4 | No external service dependencies (fully self-contained) |

---

## 6. Non-Functional Requirements

### 6.1 Usability
| ID | Requirement |
|----|-------------|
| U1 | Zero configuration needed for basic usage |
| U2 | Clear, actionable error messages |
| U3 | Comprehensive --help for all commands |
| U4 | Quick start: working in < 5 minutes |

### 6.2 Reliability
| ID | Requirement |
|----|-------------|
| R1 | Graceful handling of malformed XML |
| R2 | Database corruption recovery |
| R3 | No data loss on crash during upload |

### 6.3 Security
| ID | Requirement |
|----|-------------|
| S1 | No external network calls (fully offline capable) |
| S2 | No telemetry or data collection |
| S3 | Safe handling of test names containing special characters |

### 6.4 Extensibility
| ID | Requirement |
|----|-------------|
| E1 | Plugin architecture for custom parsers |
| E2 | Custom analysis rules via configuration |
| E3 | API for programmatic access |

---

## 7. User Stories

### MVP User Stories

```
US-001: Upload Test Results
AS A QA engineer
I WANT TO upload my JUnit XML test results
SO THAT Flaktor can track my test history

Acceptance Criteria:
- Can upload single XML file
- Can upload directory of XML files
- Results are stored with run metadata
- Duplicate uploads are handled gracefully
```

```
US-002: View Flaky Tests
AS A QA engineer
I WANT TO see which tests are flaky
SO THAT I can prioritize which tests to fix

Acceptance Criteria:
- List shows test name, flakiness score, last 5 statuses
- Sorted by flakiness score (highest first)
- Can filter by minimum flakiness threshold
- Shows trend indicator (improving/worsening)
```

```
US-003: Investigate Specific Test
AS A developer
I WANT TO see the history of a specific test
SO THAT I can understand its failure pattern

Acceptance Criteria:
- Shows last N runs with pass/fail status
- Shows failure messages for failed runs
- Shows when test started being flaky
- Shows associated commit/branch info
```

```
US-004: CI Integration
AS A DevOps engineer
I WANT TO integrate Flaktor into our CI pipeline
SO THAT flaky tests are automatically tracked

Acceptance Criteria:
- Single command to upload results
- Exit code reflects flakiness status
- Can configure flakiness threshold for warnings/failures
- Works in GitHub Actions, GitLab CI, Jenkins
```

```
US-005: Generate Report
AS AN engineering manager
I WANT TO generate a test health report
SO THAT I can share test suite status with stakeholders

Acceptance Criteria:
- HTML report with charts
- Summary statistics
- Trend over time
- Exportable as PDF (via browser print)
```

---

## 8. Success Metrics

### Adoption Metrics
| Metric | Target (6 months) |
|--------|-------------------|
| GitHub stars | 500+ |
| PyPI downloads/month | 1,000+ |
| Active GitHub issues/discussions | 50+ |
| Contributors | 5+ |

### User Success Metrics
| Metric | How to Measure |
|--------|----------------|
| Time to first insight | < 5 minutes from install to first flaky test identified |
| Tests identified | Average 10+ flaky tests discovered per new user |
| CI integration time | < 30 minutes to add to existing pipeline |

### Quality Metrics
| Metric | Target |
|--------|--------|
| Test coverage | 80%+ |
| CLI response time | < 2 seconds |
| Zero critical bugs | In production for 30+ days |

---

## 9. Out of Scope (Not in MVP)

| Feature | Reason |
|---------|--------|
| Real-time test monitoring | Requires running alongside tests, too invasive |
| Auto-fix flaky tests | Too complex, varies by framework |
| Paid/hosted version | Focus on open-source first |
| Mobile app | No user need identified |
| Test execution | We analyze results, not run tests |
| Code coverage integration | Separate concern, can add later |

---

## 10. Risks & Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| JUnit XML format variations | Medium | High | Test with many real-world samples, lenient parser |
| SQLite scale limits | Medium | Low | Document limits, provide PostgreSQL option later |
| Low adoption | High | Medium | Focus on documentation, easy onboarding |
| Competitor launches similar tool | Medium | Medium | Move fast, build community, stay open-source |

---

## 11. Open Questions

1. Should we support a hosted/SaaS version in the future?
2. What's the best way to correlate test runs with git commits in various CI systems?
3. Should we integrate with test management tools (TestRail, Zephyr)?
4. How do we handle very large test suites (100k+ tests)?

---

## 12. Appendix

### A. Flakiness Score Algorithm

```
Flakiness Score = (Status Transitions / Total Runs - 1) * 100

Where:
- Status Transition = result differs from previous run
- Minimum 5 runs required for calculation
- Looking at last 30 runs by default

Example:
- Runs: P P F P F P F P F P (10 runs)
- Transitions: 7 (P->F, F->P, P->F, F->P, P->F, F->P, F->P)
- Score: (7 / 9) * 100 = 77.8% flaky
```

### B. Test Classification

| Classification | Criteria |
|----------------|----------|
| Stable Pass | 100% pass rate, 0 transitions |
| Stable Fail | 100% fail rate, 0 transitions |
| Flaky | >10% transition rate |
| Improving | Flakiness score decreasing over time |
| Worsening | Flakiness score increasing over time |
| New | < 5 runs, insufficient data |

### C. Supported JUnit XML Elements

```xml
<testsuites>
  <testsuite name="..." tests="..." failures="..." errors="..." time="...">
    <testcase name="..." classname="..." time="...">
      <failure message="..." type="...">Stack trace</failure>
      <error message="..." type="...">Stack trace</error>
      <skipped message="..."/>
    </testcase>
  </testsuite>
</testsuites>
```

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-01-15 | - | Initial requirements |

---

*This is a living document. Update as requirements evolve.*
