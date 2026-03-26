/* AI Workflow Benchmark - Leaderboard Interactivity */

document.addEventListener("DOMContentLoaded", function () {
    initSorting();
    initFilter();
    animateScores();
    drawRadarChart();
});

/* Column sorting */
function initSorting() {
    var headers = document.querySelectorAll("#leaderboard-table thead th[data-sort]");
    headers.forEach(function (th) {
        th.addEventListener("click", function () {
            var table = document.getElementById("leaderboard-table");
            var tbody = table.querySelector("tbody");
            var rows = Array.from(tbody.querySelectorAll("tr"));
            var sortKey = th.dataset.sort;
            var colIndex = Array.from(th.parentNode.children).indexOf(th);

            var isDesc = th.classList.contains("sort-desc");
            headers.forEach(function (h) {
                h.classList.remove("sort-active", "sort-asc", "sort-desc");
            });

            var direction = isDesc ? "asc" : "desc";
            th.classList.add("sort-active", "sort-" + direction);

            rows.sort(function (a, b) {
                var aVal = extractValue(a.children[colIndex]);
                var bVal = extractValue(b.children[colIndex]);
                if (direction === "asc") return aVal - bVal;
                return bVal - aVal;
            });

            rows.forEach(function (row, i) {
                row.querySelector(".rank").textContent = i + 1;
                tbody.appendChild(row);
            });
        });
    });
}

function extractValue(td) {
    var text = td.textContent.replace(/[$%,]/g, "").trim();
    var num = parseFloat(text);
    return isNaN(num) ? 0 : num;
}

/* Filter */
function initFilter() {
    var input = document.getElementById("filter-input");
    if (!input) return;

    input.addEventListener("input", function () {
        var query = input.value.toLowerCase();
        var rows = document.querySelectorAll("#leaderboard-table tbody tr");
        rows.forEach(function (row) {
            var toolName = (row.dataset.tool || "").toLowerCase();
            row.style.display = toolName.indexOf(query) !== -1 ? "" : "none";
        });
    });
}

/* Animate score numbers */
function animateScores() {
    var elements = document.querySelectorAll("[data-target]");
    elements.forEach(function (el) {
        var target = parseFloat(el.dataset.target);
        var duration = 800;
        var start = performance.now();

        function tick(now) {
            var elapsed = now - start;
            var progress = Math.min(elapsed / duration, 1);
            var eased = 1 - Math.pow(1 - progress, 3);
            var current = (target * eased).toFixed(1);
            el.textContent = current;
            if (progress < 1) requestAnimationFrame(tick);
            else el.textContent = target;
        }
        requestAnimationFrame(tick);
    });
}

/* Radar chart using Chart.js */
function drawRadarChart() {
    var canvas = document.getElementById("radar-chart");
    if (!canvas || typeof Chart === "undefined") return;
    if (typeof RESULTS_DATA === "undefined" || RESULTS_DATA.length === 0) return;

    var metrics = [
        "Success Rate",
        "Partial Credit",
        "Cost Efficiency",
        "Code Quality",
        "Speed",
        "Low Regressions",
        "Security",
        "Few Iterations"
    ];
    var colors = ["#3b82f6", "#22c55e", "#eab308", "#ef4444", "#a855f7", "#06b6d4"];

    // Aggregate by tool
    var toolData = {};
    RESULTS_DATA.forEach(function (r) {
        if (!toolData[r.tool]) {
            toolData[r.tool] = {
                count: 0, success: 0, score: 0, maxScore: 0,
                time: 0, cost: 0, iterations: 0, lint: 0, security: 0, regressions: 0
            };
        }
        var t = toolData[r.tool];
        t.count++;
        if (r.outcome.success) t.success++;
        t.score += r.outcome.partial_credit_score;
        t.maxScore += r.outcome.partial_credit_max;
        t.time += r.metrics.wall_clock_seconds;
        t.cost += r.cost.estimated_cost_usd;
        t.iterations += r.metrics.iteration_count;
        t.lint += Math.abs(r.quality.lint_delta);
        t.security += Math.abs(r.quality.security_delta);
        t.regressions += r.quality.test_regressions;
    });

    function normalize(s) {
        var n = s.count || 1;
        return [
            s.success / n * 100,
            s.maxScore > 0 ? s.score / s.maxScore * 100 : 0,
            Math.max(0, Math.min(100, (1 - s.cost / n / 2) * 100)),
            Math.max(0, 100 - s.lint / n * 10),
            Math.max(0, Math.min(100, (1 - s.time / n / 600) * 100)),
            Math.max(0, 100 - s.regressions / n * 50),
            Math.max(0, 100 - s.security / n * 25),
            Math.max(0, Math.min(100, (1 - s.iterations / n / 20) * 100))
        ];
    }

    var datasets = Object.entries(toolData).map(function (entry, i) {
        var name = entry[0];
        var stats = entry[1];
        var color = colors[i % colors.length];
        return {
            label: name,
            data: normalize(stats),
            borderColor: color,
            backgroundColor: color + "33",
            pointRadius: 3,
        };
    });

    new Chart(canvas.getContext("2d"), {
        type: "radar",
        data: { labels: metrics, datasets: datasets },
        options: {
            scales: {
                r: {
                    beginAtZero: true,
                    max: 100,
                    ticks: { stepSize: 20, color: "#94a3b8" },
                    grid: { color: "#334155" },
                    pointLabels: { color: "#94a3b8", font: { size: 11 } },
                }
            },
            plugins: {
                legend: { position: "bottom", labels: { color: "#e2e8f0" } }
            },
        },
    });
}

/* CSV export */
function exportCSV() {
    if (typeof RESULTS_DATA === "undefined") return;
    var rows = [["task_id", "tool", "success", "score", "time_s", "cost_usd"]];
    RESULTS_DATA.forEach(function (r) {
        rows.push([
            r.task_id,
            r.tool,
            r.outcome && r.outcome.success ? "PASS" : "FAIL",
            r.outcome && r.outcome.partial_credit_score || 0,
            r.metrics && r.metrics.wall_clock_seconds || 0,
            r.cost && r.cost.estimated_cost_usd || 0,
        ]);
    });
    var csv = rows.map(function (r) { return r.join(","); }).join("\n");
    var blob = new Blob([csv], { type: "text/csv" });
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url;
    a.download = "awb-results.csv";
    a.click();
    URL.revokeObjectURL(url);
}
