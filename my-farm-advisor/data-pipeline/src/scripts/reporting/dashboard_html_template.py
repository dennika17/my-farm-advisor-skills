#!/usr/bin/env python3
"""HTML template and inline JavaScript for the Grower Field Weather Dashboard.

Produces a single self-contained HTML file with zero runtime external dependencies.
Uses string replacement instead of f-string to avoid brace escaping issues.
"""

from __future__ import annotations


def _sanitize_js_string(value: str) -> str:
    """Escape a string for safe inclusion in a JS string literal."""
    return (
        value.replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
    )


# Base HTML template with placeholders for dynamic content.
# All JS/CSS braces are literal (no format expressions inside the template string).
_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Grower Field Weather Dashboard — __FARM_NAME__</title>
<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
  background: #f4f5f7;
  color: #1e293b;
  line-height: 1.45;
  height: 100vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
header {
  flex-shrink: 0;
  background: #fff;
  border-bottom: 1px solid #e2e8f0;
  padding: 0.6rem 1rem;
  display: flex;
  align-items: center;
  gap: 1rem;
  flex-wrap: wrap;
}
header h1 {
  font-size: 1.1rem;
  font-weight: 700;
  color: #0f172a;
  white-space: nowrap;
}
header .subtitle {
  font-size: 0.82rem;
  color: #64748b;
}
header .note {
  font-size: 0.75rem;
  color: #94a3b8;
  margin-left: auto;
}
.controls {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}
.dropdown-wrap {
  position: relative;
  display: inline-block;
}
.dropdown-toggle {
  background: #fff;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  padding: 0.35rem 0.7rem;
  font-size: 0.82rem;
  cursor: pointer;
  min-width: 140px;
  text-align: left;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.4rem;
}
.dropdown-toggle:hover, .dropdown-toggle:focus {
  border-color: #2563eb;
  outline: none;
}
.dropdown-toggle .caret {
  border-left: 4px solid transparent;
  border-right: 4px solid transparent;
  border-top: 4px solid #64748b;
  display: inline-block;
  width: 0; height: 0;
}
.dropdown-menu {
  display: none;
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  box-shadow: 0 10px 25px rgba(0,0,0,0.12);
  min-width: 220px;
  max-width: 320px;
  max-height: 320px;
  overflow-y: auto;
  z-index: 100;
  padding: 0.4rem 0;
}
.dropdown-menu.open { display: block; }
.dropdown-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.35rem 0.7rem;
  font-size: 0.82rem;
  cursor: pointer;
  user-select: none;
}
.dropdown-item:hover { background: #f1f5f9; }
.dropdown-item input[type="checkbox"] {
  width: 14px; height: 14px; cursor: pointer; flex-shrink: 0;
}
.dropdown-item label { cursor: pointer; flex: 1; }
.dropdown-item .nodata {
  color: #94a3b8;
  font-size: 0.75rem;
  margin-left: auto;
}
.dropdown-actions {
  display: flex;
  gap: 0.5rem;
  padding: 0.3rem 0.7rem 0.5rem;
  border-top: 1px solid #f1f5f9;
  margin-top: 0.2rem;
}
.dropdown-actions button {
  background: transparent;
  border: 1px solid #cbd5e1;
  border-radius: 4px;
  padding: 0.2rem 0.5rem;
  font-size: 0.75rem;
  cursor: pointer;
  color: #334155;
}
.dropdown-actions button:hover { background: #f1f5f9; }
.summary {
  font-size: 0.82rem;
  color: #475569;
  white-space: nowrap;
}
.reset-btn {
  background: #2563eb;
  color: #fff;
  border: none;
  border-radius: 6px;
  padding: 0.35rem 0.8rem;
  font-size: 0.82rem;
  cursor: pointer;
}
.reset-btn:hover { background: #1d4ed8; }
main {
  flex: 1;
  display: flex;
  min-height: 0;
  gap: 0.5rem;
  padding: 0.5rem;
}
.panel-left, .panel-right {
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.panel-left { flex: 1 1 50%; }
.panel-right { flex: 1 1 50%; display: flex; flex-direction: column; gap: 0.5rem; }
.chart-box {
  flex: 1 1 50%;
  min-height: 0;
  position: relative;
}
.empty-state {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #94a3b8;
  font-size: 0.9rem;
  text-align: center;
  padding: 1rem;
  pointer-events: none;
}
@media (max-width: 900px) {
  main { flex-direction: column; }
  .panel-left, .panel-right { flex: 1 1 auto; min-height: 300px; }
}
</style>
</head>
<body>
<header>
  <div>
    <h1>Grower Field Weather Dashboard</h1>
    <div class="subtitle">__FARM_NAME__</div>
  </div>
  <div class="controls">
    <div class="dropdown-wrap" id="fieldDropdownWrap">
      <button class="dropdown-toggle" id="fieldToggle" aria-haspopup="true" aria-expanded="false">
        Fields <span class="caret"></span>
      </button>
      <div class="dropdown-menu" id="fieldMenu" role="menu"></div>
    </div>
    <div class="dropdown-wrap" id="yearDropdownWrap">
      <button class="dropdown-toggle" id="yearToggle" aria-haspopup="true" aria-expanded="false">
        Years <span class="caret"></span>
      </button>
      <div class="dropdown-menu" id="yearMenu" role="menu"></div>
    </div>
    <span class="summary" id="summaryText"></span>
    <button class="reset-btn" id="resetBtn">Reset view</button>
  </div>
  <div class="note" id="basemapNote">__NO_BASEMAP_NOTE__</div>
</header>
<main>
  <div class="panel-left" id="mapPanel"></div>
  <div class="panel-right">
    <div class="chart-box" id="gddPanel"><div class="empty-state" id="gddEmpty">Select field-year combinations with weather data to view Growing Degree Days.</div></div>
    <div class="chart-box" id="rainPanel"><div class="empty-state" id="rainEmpty">Select field-year combinations with weather data to view Rainfall.</div></div>
  </div>
</main>

<script>
__PLOTLY_BUNDLE__
</script>

<script>
(function() {
'use strict';

var FARM = { farmId: '__FARM_ID__', farmName: '__FARM_NAME__', generatedAt: '__GENERATED_AT__', basemapAvailable: __BASEMAP_AVAILABLE__ };
var FIELDS = __FIELDS_JSON__;
var WEATHER = __WEATHER_JSON__;
var BASEMAP_B64 = '__BASEMAP_B64__';

var PALETTE = ['#1f77b4','#ff7f0e','#2ca02c','#d62728','#9467bd','#8c564b','#e377c2','#7f7f7f','#bcbd22','#17becf'];
var fieldColorMap = {};
FIELDS.forEach(function(f, i) { fieldColorMap[f.fieldId] = PALETTE[i % PALETTE.length]; });

var selectedFields = new Set(FIELDS.map(function(f) { return f.fieldId; }));
var selectedYears = new Set();
var sharedXRange = [80, 320];
var isRelayouting = false;

var allYears = [];
var yearSet = new Set();
WEATHER.forEach(function(w) { yearSet.add(w.year); });
allYears = Array.from(yearSet).sort(function(a,b){ return a-b; });
if (allYears.length > 0) {
  if (yearSet.has(2025)) { selectedYears.add(2025); }
  else { selectedYears.add(allYears[allYears.length - 1]); }
}

var mapPanel = document.getElementById('mapPanel');
var gddPanel = document.getElementById('gddPanel');
var rainPanel = document.getElementById('rainPanel');
var gddEmpty = document.getElementById('gddEmpty');
var rainEmpty = document.getElementById('rainEmpty');
var summaryText = document.getElementById('summaryText');
var fieldToggle = document.getElementById('fieldToggle');
var fieldMenu = document.getElementById('fieldMenu');
var yearToggle = document.getElementById('yearToggle');
var yearMenu = document.getElementById('yearMenu');
var resetBtn = document.getElementById('resetBtn');

function fmt(n) { return (typeof n === 'number') ? n.toFixed(1) : String(n); }

function buildFieldMenu() {
  var html = '<div class="dropdown-actions"><button onclick="window._selectAllFields()">Select all</button><button onclick="window._clearAllFields()">Clear all</button></div>';
  FIELDS.forEach(function(f) {
    var checked = selectedFields.has(f.fieldId) ? 'checked' : '';
    var nodata = f.hasWeatherData ? '' : '<span class="nodata">(no data)</span>';
    html += '<div class="dropdown-item" data-field-id="' + f.fieldId + '">' +
      '<input type="checkbox" ' + checked + ' data-field-id="' + f.fieldId + '">' +
      '<label>' + f.fieldName + '</label>' + nodata + '</div>';
  });
  fieldMenu.innerHTML = html;
  fieldToggle.innerHTML = 'Fields (' + selectedFields.size + '/' + FIELDS.length + ') <span class="caret"></span>';
}

function buildYearMenu() {
  if (allYears.length === 0) {
    yearMenu.innerHTML = '<div class="dropdown-item"><span class="nodata">No weather years available</span></div>';
    yearToggle.innerHTML = 'Years (0) <span class="caret"></span>';
    return;
  }
  var html = '<div class="dropdown-actions"><button onclick="window._selectAllYears()">Select all</button><button onclick="window._clearAllYears()">Clear all</button></div>';
  allYears.forEach(function(y) {
    var checked = selectedYears.has(y) ? 'checked' : '';
    html += '<div class="dropdown-item" data-year="' + y + '">' +
      '<input type="checkbox" ' + checked + ' data-year="' + y + '">' +
      '<label>' + y + '</label></div>';
  });
  yearMenu.innerHTML = html;
  yearToggle.innerHTML = 'Years (' + selectedYears.size + '/' + allYears.length + ') <span class="caret"></span>';
}

function updateSummary() {
  var comboCount = 0;
  WEATHER.forEach(function(w) { if (selectedFields.has(w.fieldId) && selectedYears.has(w.year)) comboCount++; });
  summaryText.textContent = selectedFields.size + ' fields, ' + selectedYears.size + ' years, ' + comboCount + ' combos';
}

window._toggleField = function(fid) {
  if (selectedFields.has(fid)) selectedFields.delete(fid); else selectedFields.add(fid);
  buildFieldMenu(); updateSummary(); renderAll();
};
window._selectAllFields = function() {
  FIELDS.forEach(function(f) { selectedFields.add(f.fieldId); });
  buildFieldMenu(); updateSummary(); renderAll();
};
window._clearAllFields = function() {
  selectedFields.clear();
  buildFieldMenu(); updateSummary(); renderAll();
};
window._toggleYear = function(y) {
  if (selectedYears.has(y)) selectedYears.delete(y); else selectedYears.add(y);
  buildYearMenu(); updateSummary(); renderAll();
};
window._selectAllYears = function() {
  allYears.forEach(function(y) { selectedYears.add(y); });
  buildYearMenu(); updateSummary(); renderAll();
};
window._clearAllYears = function() {
  selectedYears.clear();
  buildYearMenu(); updateSummary(); renderAll();
};

function setupDropdown(toggle, menu) {
  toggle.addEventListener('click', function(e) {
    e.stopPropagation();
    var open = menu.classList.contains('open');
    document.querySelectorAll('.dropdown-menu.open').forEach(function(m) { m.classList.remove('open'); });
    if (!open) menu.classList.add('open');
    toggle.setAttribute('aria-expanded', String(!open));
  });
}
setupDropdown(fieldToggle, fieldMenu);
setupDropdown(yearToggle, yearMenu);

// Event delegation for dropdown item clicks (fields)
fieldMenu.addEventListener('click', function(e) {
  var item = e.target.closest('.dropdown-item');
  if (!item) return;
  var fid = item.getAttribute('data-field-id');
  if (!fid) return;
  e.stopPropagation();
  window._toggleField(fid);
});

// Event delegation for dropdown item clicks (years)
yearMenu.addEventListener('click', function(e) {
  var item = e.target.closest('.dropdown-item');
  if (!item) return;
  var y = item.getAttribute('data-year');
  if (!y) return;
  e.stopPropagation();
  window._toggleYear(parseInt(y, 10));
});

document.addEventListener('click', function() {
  document.querySelectorAll('.dropdown-menu.open').forEach(function(m) { m.classList.remove('open'); });
  fieldToggle.setAttribute('aria-expanded', 'false');
  yearToggle.setAttribute('aria-expanded', 'false');
});

resetBtn.addEventListener('click', function() {
  selectedFields = new Set(FIELDS.map(function(f) { return f.fieldId; }));
  selectedYears.clear();
  if (allYears.length > 0) {
    if (allYears.indexOf(2025) >= 0) selectedYears.add(2025);
    else selectedYears.add(allYears[allYears.length - 1]);
  }
  sharedXRange = [80, 320];
  buildFieldMenu(); buildYearMenu(); updateSummary(); renderAll();
});

function buildMapTraces() {
  var traces = [];
  var anySelected = selectedFields.size > 0;
  var selBounds = { xs: [], ys: [] };

  FIELDS.forEach(function(f) {
    var isSel = selectedFields.has(f.fieldId);
    var color = fieldColorMap[f.fieldId];
    var fillAlpha = isSel ? '99' : '22';
    var lineWidth = isSel ? 2.5 : 1;
    var z = isSel ? 10 : 1;

    f.mercatorPolygons.forEach(function(poly) {
      var xs = poly.map(function(p) { return p[0]; });
      var ys = poly.map(function(p) { return p[1]; });
      if (xs.length > 0 && (xs[0] !== xs[xs.length-1] || ys[0] !== ys[ys.length-1])) {
        xs.push(xs[0]); ys.push(ys[0]);
      }
      traces.push({
        x: xs, y: ys, mode: 'lines', fill: 'toself',
        fillcolor: color + fillAlpha,
        line: { color: color, width: lineWidth },
        hoverinfo: 'text',
        text: f.fieldName + '<br>' + fmt(f.acres) + ' ac',
        name: f.fieldName,
        showlegend: false,
        customdata: [f.fieldId],
        traceIndex: traces.length,
        zindex: z
      });
    });

    if (anySelected && isSel) {
      f.mercatorPolygons.forEach(function(poly) {
        poly.forEach(function(p) { selBounds.xs.push(p[0]); selBounds.ys.push(p[1]); });
      });
    } else if (!anySelected) {
      f.mercatorPolygons.forEach(function(poly) {
        poly.forEach(function(p) { selBounds.xs.push(p[0]); selBounds.ys.push(p[1]); });
      });
    }
  });

  var range = {};
  if (selBounds.xs.length > 0) {
    var minx = Math.min.apply(null, selBounds.xs);
    var maxx = Math.max.apply(null, selBounds.xs);
    var miny = Math.min.apply(null, selBounds.ys);
    var maxy = Math.max.apply(null, selBounds.ys);
    var bfx = (maxx - minx) * 0.2 || 1000;
    var bfy = (maxy - miny) * 0.2 || 1000;
    range = { x: [minx - bfx, maxx + bfx], y: [miny - bfy, maxy + bfy] };
  } else if (FIELDS.length > 0) {
    var allXs = [], allYs = [];
    FIELDS.forEach(function(f) {
      f.mercatorPolygons.forEach(function(poly) {
        poly.forEach(function(p) { allXs.push(p[0]); allYs.push(p[1]); });
      });
    });
    var minx = Math.min.apply(null, allXs);
    var maxx = Math.max.apply(null, allXs);
    var miny = Math.min.apply(null, allYs);
    var maxy = Math.max.apply(null, allYs);
    var bfx = (maxx - minx) * 0.2 || 1000;
    var bfy = (maxy - miny) * 0.2 || 1000;
    range = { x: [minx - bfx, maxx + bfx], y: [miny - bfy, maxy + bfy] };
  }

  return { traces: traces, range: range };
}

function renderMap() {
  var mapData = buildMapTraces();
  var layout = {
    margin: { t: 10, b: 10, l: 10, r: 10 },
    paper_bgcolor: '#fff',
    plot_bgcolor: FARM.basemapAvailable ? '#fff' : '#e8e8e8',
    xaxis: {
      visible: false,
      range: mapData.range.x,
      scaleanchor: 'y',
      scaleratio: 1,
      constrain: 'domain'
    },
    yaxis: {
      visible: false,
      range: mapData.range.y,
      constrain: 'domain'
    },
    showlegend: false,
    hovermode: 'closest',
    dragmode: 'pan'
  };

  if (FARM.basemapAvailable && BASEMAP_B64) {
    var allXs = [], allYs = [];
    FIELDS.forEach(function(f) {
      f.mercatorPolygons.forEach(function(poly) {
        poly.forEach(function(p) { allXs.push(p[0]); allYs.push(p[1]); });
      });
    });
    var minx = Math.min.apply(null, allXs);
    var maxx = Math.max.apply(null, allXs);
    var miny = Math.min.apply(null, allYs);
    var maxy = Math.max.apply(null, allYs);
    layout.images = [{
      source: BASEMAP_B64,
      xref: 'x',
      yref: 'y',
      x: minx,
      y: maxy,
      sizex: maxx - minx,
      sizey: maxy - miny,
      sizing: 'stretch',
      opacity: 1,
      layer: 'below'
    }];
  }

  var config = { displayModeBar: false, scrollZoom: true };
  Plotly.newPlot('mapPanel', mapData.traces, layout, config);

  var mapEl = document.getElementById('mapPanel');
  mapEl.on('plotly_click', function(data) {
    if (data.points && data.points.length > 0) {
      var fid = data.points[0].customdata;
      if (fid) { window._toggleField(fid); }
    }
  });
}

function getActiveRecords() {
  var out = [];
  WEATHER.forEach(function(w) { if (selectedFields.has(w.fieldId) && selectedYears.has(w.year)) out.push(w); });
  return out;
}

function buildGddTraces() {
  var records = getActiveRecords();
  var traces = [];
  records.forEach(function(w) {
    var color = fieldColorMap[w.fieldId];
    var fieldName = '';
    FIELDS.forEach(function(f) { if (f.fieldId === w.fieldId) fieldName = f.fieldName; });
    var xs = w.daily.map(function(d) { return d.dayOfYear; });
    var ys = w.daily.map(function(d) { return d.cumulativeGdd; });
    var dates = w.daily.map(function(d) { return d.date; });
    traces.push({
      x: xs, y: ys, mode: 'lines',
      name: fieldName + ' ' + w.year,
      line: { color: color, width: 2 },
      customdata: dates,
      hovertemplate:
        '<b>%{data.name}</b><br>Date: %{customdata}<br>Day of Year: %{x}<br>Cumulative GDD: %{y:.1f}<extra></extra>'
    });
    if (w.lastFrostDoy) {
      traces.push({
        x: [w.lastFrostDoy, w.lastFrostDoy],
        y: [0, 1],
        mode: 'lines',
        line: { color: color, width: 1.5, dash: 'dot' },
        yref: 'paper',
        opacity: 0.6,
        showlegend: false,
        hoverinfo: 'skip'
      });
    }
  });
  return traces;
}

function buildRainTraces() {
  var records = getActiveRecords();
  var barTraces = [];
  var lineTraces = [];
  records.forEach(function(w) {
    var color = fieldColorMap[w.fieldId];
    var fieldName = '';
    FIELDS.forEach(function(f) { if (f.fieldId === w.fieldId) fieldName = f.fieldName; });
    var xs = w.daily.map(function(d) { return d.dayOfYear; });
    var daily = w.daily.map(function(d) { return d.dailyRainfallIn; });
    var cum = w.daily.map(function(d) { return d.cumulativeRainfallIn; });
    var dates = w.daily.map(function(d) { return d.date; });
    barTraces.push({
      x: xs, y: daily, type: 'bar',
      name: fieldName + ' ' + w.year + ' daily',
      marker: { color: color, opacity: 0.25 },
      yaxis: 'y',
      customdata: dates,
      hovertemplate:
        '<b>%{data.name}</b><br>Date: %{customdata}<br>Day of Year: %{x}<br>Daily rainfall: %{y:.2f} in<extra></extra>'
    });
    lineTraces.push({
      x: xs, y: cum, mode: 'lines',
      name: fieldName + ' ' + w.year + ' cumulative',
      line: { color: color, width: 2 },
      yaxis: 'y2',
      customdata: dates,
      hovertemplate:
        '<b>%{data.name}</b><br>Date: %{customdata}<br>Day of Year: %{x}<br>Cumulative rainfall: %{y:.2f} in<extra></extra>'
    });
  });
  return barTraces.concat(lineTraces);
}

function renderCharts() {
  var gddTraces = buildGddTraces();
  var rainTraces = buildRainTraces();

  gddEmpty.style.display = gddTraces.length > 0 ? 'none' : 'flex';
  rainEmpty.style.display = rainTraces.length > 0 ? 'none' : 'flex';

  var hasData = gddTraces.length > 0;
  var xRange = sharedXRange;
  if (hasData) {
    var allDoy = [];
    gddTraces.forEach(function(t) { if (t.x) t.x.forEach(function(v) { allDoy.push(v); }); });
    if (allDoy.length > 0) {
      var minD = Math.min.apply(null, allDoy);
      var maxD = Math.max.apply(null, allDoy);
      if (maxD - minD < 100) {
        xRange = [Math.max(1, minD - 20), Math.min(366, maxD + 20)];
      } else if (minD < 80 || maxD > 320) {
        xRange = [Math.max(1, minD - 10), Math.min(366, maxD + 10)];
      }
    }
  }

  var gddLayout = {
    title: { text: 'Growing Degree Days', font: { size: 14 } },
    margin: { t: 40, b: 40, l: 50, r: 20 },
    paper_bgcolor: '#fff',
    plot_bgcolor: '#fff',
    xaxis: {
      title: 'Day of Year',
      dtick: 30,
      range: xRange.slice(),
      showgrid: true,
      gridcolor: '#f1f5f9'
    },
    yaxis: {
      title: 'Cumulative GDD (base 10°C)',
      showgrid: true,
      gridcolor: '#f1f5f9'
    },
    legend: { orientation: 'h', y: 1.12, x: 1, xanchor: 'right' },
    hovermode: 'closest'
  };

  var rainLayout = {
    title: { text: 'Rainfall', font: { size: 14 } },
    margin: { t: 40, b: 40, l: 50, r: 50 },
    paper_bgcolor: '#fff',
    plot_bgcolor: '#fff',
    xaxis: {
      title: 'Day of Year',
      dtick: 30,
      range: xRange.slice(),
      showgrid: true,
      gridcolor: '#f1f5f9'
    },
    yaxis: {
      title: 'Daily rainfall (in)',
      showgrid: true,
      gridcolor: '#f1f5f9'
    },
    yaxis2: {
      title: 'Cumulative rainfall (in)',
      overlaying: 'y',
      side: 'right',
      showgrid: false
    },
    legend: { orientation: 'h', y: 1.12, x: 1, xanchor: 'right' },
    hovermode: 'closest',
    barmode: 'group'
  };

  var config = { displayModeBar: false, scrollZoom: false };

  Plotly.newPlot('gddPanel', gddTraces, gddLayout, config);
  Plotly.newPlot('rainPanel', rainTraces, rainLayout, config);

  function linkRelayout(sourceId, targetId) {
    var source = document.getElementById(sourceId);
    source.on('plotly_relayout', function(data) {
      if (isRelayouting) return;
      var xrange = data['xaxis.range[0]'] !== undefined ? [data['xaxis.range[0]'], data['xaxis.range[1]']] : null;
      if (!xrange && data.xaxis && data.xaxis.range) xrange = data.xaxis.range;
      if (!xrange) return;
      sharedXRange = [xrange[0], xrange[1]];
      isRelayouting = true;
      Plotly.relayout(targetId, { 'xaxis.range': xrange.slice() });
      isRelayouting = false;
    });
  }
  linkRelayout('gddPanel', 'rainPanel');
  linkRelayout('rainPanel', 'gddPanel');
}

function renderAll() {
  renderMap();
  renderCharts();
}

buildFieldMenu();
buildYearMenu();
updateSummary();
renderAll();
})();
</script>
</body>
</html>"""


def build_html(
    *,
    farm_id: str,
    farm_name: str,
    generated_at: str,
    basemap_available: bool,
    basemap_b64: str,
    fields_json: str,
    weather_json: str,
    plotly_bundle: str,
    no_basemap_note: str = "",
) -> str:
    """Return the complete self-contained HTML string."""
    html = _HTML_TEMPLATE
    html = html.replace("__FARM_NAME__", _sanitize_js_string(farm_name))
    html = html.replace("__FARM_ID__", _sanitize_js_string(farm_id))
    html = html.replace("__GENERATED_AT__", _sanitize_js_string(generated_at))
    html = html.replace("__BASEMAP_AVAILABLE__", "true" if basemap_available else "false")
    html = html.replace("__FIELDS_JSON__", fields_json)
    html = html.replace("__WEATHER_JSON__", weather_json)
    html = html.replace("__BASEMAP_B64__", basemap_b64)
    html = html.replace("__NO_BASEMAP_NOTE__", _sanitize_js_string(no_basemap_note))
    html = html.replace("__PLOTLY_BUNDLE__", plotly_bundle)
    return html
