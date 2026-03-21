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

/* Radar chart using Canvas API */
function drawRadarChart() {
    var canvas = document.getElementById("radar-chart");
    if (!canvas || typeof RESULTS_DATA === "undefined" || RESULTS_DATA.length === 0) return;

    var ctx = canvas.getContext("2d");
    var w = canvas.width;
    var h = canvas.height;
    var cx = w / 2;
    var cy = h / 2;
    var radius = Math.min(cx, cy) - 60;

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
    var numAxes = metrics.length;
    var angleStep = (2 * Math.PI) / numAxes;

    // Aggregate by tool
    var toolData = {};
    RESULTS_DATA.forEach(function (r) {
        if (!toolData[r.tool]) {
            toolData[r.tool] = { count: 0, success: 0, score: 0, maxScore: 0, time: 0, cost: 0, iterations: 0, lint: 0, security: 0, regressions: 0 };
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

    var colors = ["#3b82f6", "#22c55e", "#eab308", "#ef4444", "#a855f7", "#06b6d4"];
    var toolNames = Object.keys(toolData);

    // Normalize to 0-100
    function normalize(toolStats) {
        var n = toolStats.count || 1;
        return [
            toolStats.success / n * 100,
            toolStats.maxScore > 0 ? toolStats.score / toolStats.maxScore * 100 : 0,
            Math.max(0, Math.min(100, (1 - toolStats.cost / n / 2) * 100)),
            Math.max(0, 100 - toolStats.lint / n * 10),
            Math.max(0, Math.min(100, (1 - toolStats.time / n / 600) * 100)),
            Math.max(0, 100 - toolStats.regressions / n * 50),
            Math.max(0, 100 - toolStats.security / n * 25),
            Math.max(0, Math.min(100, (1 - toolStats.iterations / n / 20) * 100))
        ];
    }

    // Clear
    ctx.fillStyle = "#1e293b";
    ctx.fillRect(0, 0, w, h);

    // Draw grid
    ctx.strokeStyle = "#334155";
    ctx.lineWidth = 0.5;
    for (var level = 1; level <= 5; level++) {
        var r = radius * level / 5;
        ctx.beginPath();
        for (var i = 0; i <= numAxes; i++) {
            var angle = i * angleStep - Math.PI / 2;
            var x = cx + r * Math.cos(angle);
            var y = cy + r * Math.sin(angle);
            if (i === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
        }
        ctx.stroke();
    }

    // Draw axes and labels
    ctx.strokeStyle = "#475569";
    ctx.fillStyle = "#94a3b8";
    ctx.font = "11px -apple-system, sans-serif";
    ctx.textAlign = "center";
    for (var i = 0; i < numAxes; i++) {
        var angle = i * angleStep - Math.PI / 2;
        ctx.beginPath();
        ctx.moveTo(cx, cy);
        ctx.lineTo(cx + radius * Math.cos(angle), cy + radius * Math.sin(angle));
        ctx.stroke();

        var labelR = radius + 20;
        var lx = cx + labelR * Math.cos(angle);
        var ly = cy + labelR * Math.sin(angle);
        ctx.fillText(metrics[i], lx, ly + 4);
    }

    // Draw tool polygons
    toolNames.forEach(function (name, idx) {
        var values = normalize(toolData[name]);
        var color = colors[idx % colors.length];

        ctx.beginPath();
        for (var i = 0; i <= numAxes; i++) {
            var j = i % numAxes;
            var angle = j * angleStep - Math.PI / 2;
            var val = values[j] / 100 * radius;
            var x = cx + val * Math.cos(angle);
            var y = cy + val * Math.sin(angle);
            if (i === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
        }
        ctx.closePath();
        ctx.fillStyle = color + "33";
        ctx.fill();
        ctx.strokeStyle = color;
        ctx.lineWidth = 2;
        ctx.stroke();
    });

    // Legend
    var legendY = h - 30;
    var legendX = 20;
    ctx.font = "12px -apple-system, sans-serif";
    toolNames.forEach(function (name, idx) {
        var color = colors[idx % colors.length];
        ctx.fillStyle = color;
        ctx.fillRect(legendX, legendY - 8, 12, 12);
        ctx.fillStyle = "#e2e8f0";
        ctx.textAlign = "left";
        ctx.fillText(name, legendX + 16, legendY + 2);
        legendX += ctx.measureText(name).width + 40;
    });
}
