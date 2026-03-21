# AWB Architecture

## System Overview

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryColor': '#2563eb', 'primaryTextColor': '#ffffff', 'primaryBorderColor': '#1d4ed8', 'secondaryColor': '#f59e0b', 'secondaryTextColor': '#1f2937', 'tertiaryColor': '#10b981', 'tertiaryTextColor': '#ffffff', 'lineColor': '#6b7280', 'fontSize': '14px'}}}%%
graph TB
    CLI["awb CLI<br/><i>Click-based</i>"]:::primary

    CLI --> Run["awb run"]:::primary
    CLI --> Gap["awb gap"]:::secondary
    CLI --> Compare["awb compare"]:::primary
    CLI --> Submit["awb submit"]:::secondary
    CLI --> Validate["awb validate"]:::tertiary
    CLI --> Leaderboard["awb leaderboard"]:::tertiary

    Run --> Runner["BenchmarkRunner<br/><i>core/runner.py</i>"]:::primary
    Gap --> GapEngine["GapReport<br/><i>analysis/gap_analysis.py</i>"]:::secondary
    Compare --> CompareEngine["compare_submissions<br/><i>submission/compare.py</i>"]:::secondary

    classDef primary fill:#2563eb,stroke:#1d4ed8,color:#fff
    classDef secondary fill:#f59e0b,stroke:#d97706,color:#1f2937
    classDef tertiary fill:#10b981,stroke:#059669,color:#fff
```

## Benchmark Run Pipeline

The core execution flow from task selection to scored result:

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryColor': '#2563eb', 'primaryTextColor': '#fff', 'lineColor': '#6b7280', 'fontSize': '13px'}}}%%
flowchart LR
    subgraph Prepare["1. Prepare"]
        direction TB
        Load["Load Task<br/>YAML"]:::blue
        Clone["Clone Repo<br/>@ Pinned SHA"]:::blue
        Setup["Run Setup<br/>Commands"]:::blue
        Load --> Clone --> Setup
    end

    subgraph Baseline["2. Baseline"]
        direction TB
        Lint1["Count Lint<br/>Warnings"]:::green
        Sec1["Count Security<br/>Issues"]:::green
        Lint1 --- Sec1
    end

    subgraph Execute["3. Execute"]
        direction TB
        Adapter["Tool Adapter<br/>execute()"]:::orange
        Stream["Parse Stream<br/>Events"]:::orange
        Metrics["Collect<br/>Metrics"]:::orange
        Adapter --> Stream --> Metrics
    end

    subgraph Verify["4. Verify"]
        direction TB
        Tests["Run Test<br/>Commands"]:::purple
        Partial["Evaluate<br/>Partial Credit"]:::purple
        Lint2["Count Lint<br/>(post)"]:::purple
        Sec2["Count Security<br/>(post)"]:::purple
        Tests --- Partial
        Lint2 --- Sec2
    end

    subgraph Score["5. Score"]
        direction TB
        Normalize["Sigmoid<br/>Normalize"]:::red
        Composite["Weighted<br/>Composite"]:::red
        Profile["Capability<br/>Profile"]:::red
        Normalize --> Composite
        Normalize --> Profile
    end

    Prepare --> Baseline --> Execute --> Verify --> Score

    classDef blue fill:#2563eb,stroke:#1d4ed8,color:#fff
    classDef green fill:#10b981,stroke:#059669,color:#fff
    classDef orange fill:#f59e0b,stroke:#d97706,color:#1f2937
    classDef purple fill:#8b5cf6,stroke:#7c3aed,color:#fff
    classDef red fill:#ef4444,stroke:#dc2626,color:#fff
```

## Module Dependency Graph

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'fontSize': '13px', 'lineColor': '#6b7280'}}}%%
graph TD
    subgraph CLI_Layer["CLI Layer"]
        CLI["cli.py"]:::blue
    end

    subgraph Core["Core"]
        Config["config.py<br/><i>Dataclasses,<br/>weights, paths</i>"]:::gray
        TaskLoader["task_loader.py<br/><i>YAML + schema<br/>validation</i>"]:::gray
        Runner["runner.py<br/><i>Async orchestrator</i>"]:::gray
        RepoMgr["repo_manager.py<br/><i>Git clone + setup</i>"]:::gray
        Results["results.py<br/><i>JSON save/load</i>"]:::gray
        MetricCol["metrics.py<br/><i>Token counting,<br/>timing</i>"]:::gray
    end

    subgraph Adapters["Adapters"]
        Base["base.py<br/><i>ToolAdapter ABC</i>"]:::orange
        Registry["registry.py"]:::orange
        CCVanilla["claude_code.py<br/><i>Vanilla</i>"]:::orange
        CCCustom["claude_code.py<br/><i>Custom</i>"]:::orange
    end

    subgraph Verification["Verification"]
        TestRun["test_runner.py"]:::green
        PartialC["partial_credit.py"]:::green
        LintChk["lint_checker.py"]:::green
        SecScan["security_scanner.py"]:::green
        DiffAna["diff_analyzer.py"]:::green
    end

    subgraph Scoring["Scoring"]
        Normalize["normalize.py<br/><i>sigmoid_normalize</i>"]:::purple
        Baselines["baselines.py<br/><i>TaskBaselines</i>"]:::purple
        Composite["composite.py<br/><i>Per-task + aggregate</i>"]:::purple
        Capabilities["capabilities.py<br/><i>Capability radar</i>"]:::purple
        Stats["statistics.py<br/><i>CI, significance</i>"]:::purple
        Integrity["integrity.py<br/><i>Contamination<br/>detection</i>"]:::purple
        Report["report.py"]:::purple
    end

    subgraph Analysis["Analysis"]
        GapAnalysis["gap_analysis.py<br/><i>Failure analysis,<br/>pattern detection</i>"]:::red
        Suggestions["suggestions.py<br/><i>Rule-based<br/>recommendations</i>"]:::red
    end

    subgraph Submission["Submission"]
        SubSchema["schema.py<br/><i>Hardware classes,<br/>dataclasses</i>"]:::teal
        Ingest["ingest.py<br/><i>Parse + validate</i>"]:::teal
        Compare["compare.py<br/><i>Cross-submission</i>"]:::teal
    end

    CLI --> Runner
    CLI --> GapAnalysis
    CLI --> Ingest
    CLI --> Compare

    Runner --> TaskLoader
    Runner --> RepoMgr
    Runner --> Registry
    Runner --> MetricCol
    Runner --> Results
    Runner --> TestRun
    Runner --> PartialC
    Runner --> LintChk
    Runner --> SecScan

    TaskLoader --> Config
    Composite --> Normalize
    Composite --> Baselines
    Capabilities --> Normalize
    Capabilities --> Baselines
    Report --> Composite
    Report --> Capabilities
    GapAnalysis --> Capabilities
    GapAnalysis --> Suggestions
    Compare --> Stats

    Registry --> Base
    CCVanilla --> Base
    CCCustom --> CCVanilla

    classDef blue fill:#2563eb,stroke:#1d4ed8,color:#fff
    classDef gray fill:#6b7280,stroke:#4b5563,color:#fff
    classDef orange fill:#f59e0b,stroke:#d97706,color:#1f2937
    classDef green fill:#10b981,stroke:#059669,color:#fff
    classDef purple fill:#8b5cf6,stroke:#7c3aed,color:#fff
    classDef red fill:#ef4444,stroke:#dc2626,color:#fff
    classDef teal fill:#14b8a6,stroke:#0d9488,color:#fff
```

## Scoring Pipeline

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'fontSize': '13px'}}}%%
flowchart TD
    subgraph Input["Raw Metrics"]
        Success["success: bool"]:::gray
        Partial["partial_credit:<br/>75/100"]:::gray
        Cost["cost: $0.85"]:::gray
        Time["time: 142s"]:::gray
        Lint["lint_delta: -2"]:::gray
        Regress["regressions: 0"]:::gray
        SecDelta["security_delta: 0"]:::gray
        Iters["iterations: 8"]:::gray
    end

    subgraph Baselines["Per-Task Baselines<br/><i>From difficulty + constraints</i>"]
        CostBase["Cost<br/>opt=$0.20<br/>base=$1.00"]:::blue
        SpeedBase["Speed<br/>opt=900s<br/>base=1800s"]:::blue
        IterBase["Iters<br/>opt=8<br/>base=20"]:::blue
    end

    subgraph Sigmoid["Sigmoid Normalize<br/><i>score = 100 / (1 + e^(k*(v-base)))</i>"]
        SigCor["Correctness<br/>87.0"]:::purple
        SigCost["Cost<br/>52.3"]:::purple
        SigSpeed["Speed<br/>91.2"]:::purple
        SigQual["Quality<br/>95.0"]:::purple
        SigRel["Reliability<br/>95.0"]:::purple
        SigSec["Security<br/>95.0"]:::purple
        SigEff["Efficiency<br/>70.1"]:::purple
    end

    subgraph Weights["Apply Weights"]
        W1["x 0.55"]:::orange
        W2["x 0.15"]:::orange
        W3["x 0.10"]:::orange
        W4["x 0.10"]:::orange
        W5["x 0.05"]:::orange
        W6["x 0.03"]:::orange
        W7["x 0.02"]:::orange
    end

    Composite["Composite<br/>Score: 82.4"]:::green

    Success --> SigCor
    Partial --> SigCor
    Cost --> CostBase --> SigCost
    Time --> SpeedBase --> SigSpeed
    Lint --> SigQual
    Regress --> SigRel
    SecDelta --> SigSec
    Iters --> IterBase --> SigEff

    SigCor --> W1 --> Composite
    SigCost --> W2 --> Composite
    SigSpeed --> W3 --> Composite
    SigQual --> W4 --> Composite
    SigRel --> W5 --> Composite
    SigSec --> W6 --> Composite
    SigEff --> W7 --> Composite

    classDef gray fill:#6b7280,stroke:#4b5563,color:#fff
    classDef blue fill:#2563eb,stroke:#1d4ed8,color:#fff
    classDef purple fill:#8b5cf6,stroke:#7c3aed,color:#fff
    classDef orange fill:#f59e0b,stroke:#d97706,color:#1f2937
    classDef green fill:#10b981,stroke:#059669,color:#fff
```

## Task Schema

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'fontSize': '12px'}}}%%
classDiagram
    class TaskDefinition {
        +str id
        +str category
        +str title
        +str difficulty
        +int estimated_minutes
        +list~str~ languages
        +list~str~ tags
        +list~str~ capabilities
        +TaskRepo repo
        +TaskVerification verification
        +TaskConstraints constraints
        +str issue_description
    }

    class TaskRepo {
        +str url
        +str commit
        +list~str~ setup_commands
    }

    class TaskVerification {
        +list~str~ test_commands
        +list~str~ lint_commands
        +list~str~ security_commands
        +list~PartialCreditCriterion~ partial_credit
    }

    class PartialCreditCriterion {
        +str criterion
        +int points
        +str check
    }

    class TaskConstraints {
        +int max_iterations
        +int timeout_seconds
    }

    class TaskBaselines {
        +float speed_optimal
        +float speed_baseline
        +float cost_optimal
        +float cost_baseline
        +int iterations_optimal
        +int iterations_baseline
        +from_task(TaskDefinition) TaskBaselines
    }

    TaskDefinition --> TaskRepo
    TaskDefinition --> TaskVerification
    TaskDefinition --> TaskConstraints
    TaskVerification --> PartialCreditCriterion
    TaskDefinition ..> TaskBaselines : derives
```

## Result Data Model

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'fontSize': '12px'}}}%%
classDiagram
    class RunResult {
        +str task_id
        +str tool
        +str run_id
        +str timestamp
        +str tool_version
        +str model
        +RunOutcome outcome
        +RunMetrics metrics
        +RunCost cost
        +RunQuality quality
        +RunEnvironment environment
        +WorkflowInfo workflow
    }

    class RunOutcome {
        +bool success
        +float partial_credit_score
        +float partial_credit_max
        +list~CriterionResult~ breakdown
    }

    class RunMetrics {
        +float wall_clock_seconds
        +int iteration_count
        +int human_interventions
        +dict tool_calls
        +int files_modified
        +int lines_changed
    }

    class RunCost {
        +int input_tokens
        +int output_tokens
        +float estimated_cost_usd
    }

    class TaskScore {
        +str task_id
        +str difficulty
        +dict per_metric
        +float composite
        +float difficulty_weight
    }

    class CapabilityProfile {
        +dict~str,CapabilityScore~ scores
        +to_dict() dict
    }

    class CapabilityScore {
        +float score
        +int tasks_tested
        +float confidence
    }

    RunResult --> RunOutcome
    RunResult --> RunMetrics
    RunResult --> RunCost
    RunResult ..> TaskScore : scored into
    TaskScore ..> CapabilityProfile : aggregated into
    CapabilityProfile --> CapabilityScore
```

## Gap Analysis Flow

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'fontSize': '13px'}}}%%
flowchart LR
    subgraph Input["Input"]
        Results["RunResult[]"]:::blue
        Tasks["TaskDefinition[]"]:::blue
    end

    subgraph Classify["Classify Failures"]
        Timeout["timeout<br/><i>>95% of limit</i>"]:::red
        TestErr["test_error<br/><i>Tests written<br/>but fail</i>"]:::red
        PartComp["partial_completion<br/><i>Some criteria<br/>pass</i>"]:::orange
        CodeErr["code_error<br/><i>Zero partial<br/>credit</i>"]:::red
    end

    subgraph Analyze["Pattern Detection"]
        CapWeak["Capability<br/>Weaknesses<br/><i>70%+ fail rate<br/>on a capability</i>"]:::purple
        DiffCliff["Difficulty<br/>Cliff<br/><i>Easy pass,<br/>hard fail</i>"]:::purple
        TokenBurn["Token<br/>Burning<br/><i>>$1 spent<br/>on failures</i>"]:::purple
    end

    subgraph Output["Gap Report"]
        Radar["Capability<br/>Radar"]:::green
        Actions["Ranked<br/>Actions"]:::green
        Suggest["Workflow<br/>Suggestions"]:::green
    end

    Results --> Classify
    Tasks --> Classify
    Classify --> Analyze
    Analyze --> Output

    classDef blue fill:#2563eb,stroke:#1d4ed8,color:#fff
    classDef red fill:#ef4444,stroke:#dc2626,color:#fff
    classDef orange fill:#f59e0b,stroke:#d97706,color:#1f2937
    classDef purple fill:#8b5cf6,stroke:#7c3aed,color:#fff
    classDef green fill:#10b981,stroke:#059669,color:#fff
```

## Tool Adapter Interface

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'fontSize': '12px'}}}%%
classDiagram
    class ToolAdapter {
        <<abstract>>
        +str name
        +str display_name
        +execute(prompt, workspace, max_turns, timeout) ToolResult*
        +check_available() bool*
        +get_config_hash() str*
        +get_version() str
    }

    class ToolResult {
        +bool success
        +int exit_code
        +str raw_output
        +list stream_events
    }

    class ClaudeCodeVanillaAdapter {
        +execute() ToolResult
        +check_available() bool
        +get_config_hash() str
    }

    class ClaudeCodeCustomAdapter {
        +execute() ToolResult
        +get_config_hash() str
        +get_version() str
    }

    class CursorAdapter {
        <<stub>>
    }

    class AiderAdapter {
        <<stub>>
    }

    ToolAdapter <|-- ClaudeCodeVanillaAdapter
    ClaudeCodeVanillaAdapter <|-- ClaudeCodeCustomAdapter
    ToolAdapter <|-- CursorAdapter
    ToolAdapter <|-- AiderAdapter
    ToolAdapter --> ToolResult
```

## Directory Structure

```
ai-workflow-benchmark/
├── awb/
│   ├── cli.py                    # Click CLI (run, gap, compare, submit, validate, leaderboard)
│   ├── core/
│   │   ├── config.py             # Dataclasses, METRIC_WEIGHTS, paths
│   │   ├── task_loader.py        # YAML + JSON Schema validation
│   │   ├── runner.py             # Async benchmark orchestrator
│   │   ├── repo_manager.py       # Git clone, setup execution
│   │   ├── results.py            # JSON save/load for RunResult
│   │   ├── metrics.py            # Token counting, stream parsing
│   │   └── timeout.py            # Task timeout wrapper
│   ├── adapters/
│   │   ├── base.py               # ToolAdapter ABC, ToolResult
│   │   ├── registry.py           # Adapter registration
│   │   ├── claude_code.py        # Vanilla + Custom variants
│   │   ├── cursor.py             # Stub
│   │   └── aider.py              # Stub
│   ├── verification/
│   │   ├── test_runner.py        # Run test_commands
│   │   ├── partial_credit.py     # Evaluate rubric criteria
│   │   ├── lint_checker.py       # Count lint issues (pre/post)
│   │   ├── security_scanner.py   # Count security issues
│   │   ├── diff_analyzer.py      # Analyze git diff
│   │   └── code_review_scorer.py # Review scoring
│   ├── scoring/
│   │   ├── normalize.py          # sigmoid_normalize + wrappers
│   │   ├── baselines.py          # TaskBaselines from difficulty
│   │   ├── composite.py          # Per-task + aggregate scoring
│   │   ├── capabilities.py       # Capability enum + radar
│   │   ├── statistics.py         # CI, significance testing
│   │   ├── integrity.py          # Contamination detection
│   │   ├── report.py             # ScoreReport + printing
│   │   └── weights.yaml          # 3 weight profiles
│   ├── analysis/
│   │   ├── gap_analysis.py       # FailureAnalysis, GapReport
│   │   └── suggestions.py        # Rule-based recommendations
│   ├── submission/
│   │   ├── schema.py             # Hardware classes, Submission
│   │   ├── ingest.py             # Parse + validate JSON
│   │   └── compare.py            # Cross-submission comparison
│   ├── workflow/
│   │   ├── descriptor.py         # Load, validate, hash
│   │   └── exporter.py           # Export current config
│   ├── leaderboard/
│   │   ├── generate.py           # HTML generation
│   │   ├── templates/            # Jinja2 templates
│   │   └── static/               # CSS/JS
│   └── tasks/
│       ├── schema.json           # Task YAML JSON Schema
│       ├── _template.yaml        # Task template
│       ├── bug-fix/              # 10 tasks (BF-001 to BF-011)
│       ├── feature-addition/     # 8 tasks (FA-001 to FA-008)
│       ├── refactoring/          # 10 tasks (RF-001 to RF-010)
│       ├── code-review/          # 7 tasks (CR-001 to CR-007)
│       ├── debugging/            # 7 tasks (DB-001 to DB-007)
│       ├── multi-file/           # 8 tasks (MF-001 to MF-008)
│       └── legacy-code/          # 10 tasks (LC-001 to LC-010)
├── tests/                        # pytest suite (71 tests)
├── results/
│   ├── schema.json               # Result JSON Schema
│   ├── submission-schema.json    # External submission schema
│   └── runs/                     # Run outputs (gitignored)
├── scripts/                      # Utility scripts
├── demos/                        # Demo GIFs
├── README.md
├── METHODOLOGY.md
├── ARCHITECTURE.md
└── pyproject.toml                # v0.2.0
```
