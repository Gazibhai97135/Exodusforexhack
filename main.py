"""
main.py — ForexSignal Pro Web Dashboard
Flask API + live dashboard served at WEBAPP_URL.
Accessible from Telegram bot's "Live Dashboard" button.
Developer: @exodus_own3r

Run: python main.py
"""

import os, logging
from flask import Flask, jsonify, render_template_string
from dotenv import load_dotenv

from engine import (
    init_db, get_signals, get_stats,
    analyze_signal, get_current_price, SYMBOLS,
)

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

app  = Flask(__name__)
PORT = int(os.getenv("WEBAPP_PORT", 5000))

# ── API ROUTES ────────────────────────────────────────────────────────────────
@app.route("/api/stats")
def api_stats():
    return jsonify(get_stats())

@app.route("/api/signals")
def api_signals():
    return jsonify(get_signals(30))

@app.route("/api/live")
def api_live():
    """Fresh signal analysis for both pairs — called every 30 s by frontend."""
    result = {}
    for sym in SYMBOLS:
        sig = analyze_signal(sym)
        result[sym] = sig if sig else {
            "symbol": sym, "direction": "NEUTRAL", "entry": 0,
        }
    return jsonify(result)

@app.route("/api/prices")
def api_prices():
    """Real-time header prices."""
    prices = {}
    for sym in SYMBOLS:
        prices[sym] = get_current_price(sym)
    return jsonify(prices)

# ── DASHBOARD HTML ────────────────────────────────────────────────────────────
DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ForexSignal Pro</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
:root{--bg:#080C14;--surf:#0F1623;--card:#161F30;--card2:#1C2840;--gold:#C9A227;--gldl:#E4C55A;--gldd:#C9A22730;--grn:#0ECB81;--grnd:#0ECB8120;--red:#F6465D;--redd:#F6465D20;--blue:#3B82F6;--t1:#EDF2FF;--t2:#8FA3C0;--t3:#4B6180;--brd:#1E2D45;--brd2:#243550;--r1:6px;--r2:10px;--r3:16px}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
body{background:var(--bg);color:var(--t1);font-family:'Inter',sans-serif;font-size:14px;line-height:1.5;min-height:100vh}
header{background:var(--surf);border-bottom:1px solid var(--brd);padding:0 20px;height:58px;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:100}
.logo{display:flex;align-items:center;gap:9px}
.logo-mark{width:30px;height:30px;background:var(--gold);border-radius:7px;display:grid;place-items:center;font-size:15px}
.logo-text{font-size:14px;font-weight:700;color:var(--t1)}.logo-text span{color:var(--gold)}
.tickers{display:flex;gap:14px}
.ticker{display:flex;align-items:center;gap:7px;background:var(--card);border:1px solid var(--brd);border-radius:18px;padding:4px 13px}
.t-sym{font-size:10px;font-weight:600;color:var(--t3);font-family:'JetBrains Mono',monospace;letter-spacing:.4px}
.t-price{font-size:12px;font-weight:600;color:var(--t1);font-family:'JetBrains Mono',monospace}
.t-chg{font-size:10px;font-family:'JetBrains Mono',monospace}
.live-badge{display:flex;align-items:center;gap:5px;font-size:11px;color:var(--t2);font-weight:500}
.dot{width:7px;height:7px;background:var(--grn);border-radius:50%;animation:pd 2s ease infinite}
@keyframes pd{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.4;transform:scale(.8)}}
main{max-width:1160px;margin:0 auto;padding:24px 18px 60px}
.lbl{font-size:10px;font-weight:600;letter-spacing:1.2px;color:var(--t3);text-transform:uppercase;margin-bottom:12px;padding-left:2px}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:24px}
.sc{background:var(--card);border:1px solid var(--brd);border-radius:var(--r2);padding:16px 18px;position:relative;overflow:hidden}
.sc::before{content:'';position:absolute;top:0;left:0;width:3px;height:100%;background:var(--gold)}
.sc:nth-child(2)::before{background:var(--grn)}.sc:nth-child(3)::before{background:var(--blue)}.sc:nth-child(4)::before{background:var(--red)}
.sl{font-size:11px;color:var(--t3);font-weight:500;margin-bottom:6px}
.sv{font-size:24px;font-weight:700;color:var(--t1);font-family:'JetBrains Mono',monospace;line-height:1;margin-bottom:3px}
.ss{font-size:11px;color:var(--t3)}
.sig-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:24px}
.sig-card{background:var(--card);border:1px solid var(--brd);border-radius:var(--r3);padding:20px;position:relative;overflow:hidden}
.sig-card.buy{border-left:3px solid var(--grn)}.sig-card.sell{border-left:3px solid var(--red)}.sig-card.neutral{border-left:3px solid var(--t3)}
.sc-top{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:16px}
.sc-sym{font-size:16px;font-weight:700;color:var(--t1);letter-spacing:-.3px}
.sc-sym small{display:block;font-size:11px;font-weight:400;color:var(--t3);margin-top:2px}
.badge{padding:4px 11px;border-radius:18px;font-size:12px;font-weight:700}
.b-buy{background:var(--grnd);color:var(--grn)}.b-sell{background:var(--redd);color:var(--red)}.b-neutral{background:var(--card2);color:var(--t3)}
.prices{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-bottom:14px}
.pb{background:var(--surf);border:1px solid var(--brd);border-radius:var(--r1);padding:9px 11px}
.pb-l{font-size:10px;color:var(--t3);font-weight:500;margin-bottom:3px}
.pb-v{font-size:12px;font-weight:600;font-family:'JetBrains Mono',monospace;color:var(--t1)}
.pb.entry .pb-v{color:var(--gldl)}.pb.tp .pb-v{color:var(--grn)}.pb.sl .pb-v{color:var(--red)}
.chips{display:flex;gap:7px;flex-wrap:wrap}
.chip{background:var(--surf);border:1px solid var(--brd);border-radius:4px;padding:3px 8px;font-size:11px;color:var(--t2);font-family:'JetBrains Mono',monospace}
.chip.gold{border-color:var(--gldd);color:var(--gold)}
.cbar{margin-top:13px}
.cbar-row{display:flex;justify-content:space-between;font-size:11px;color:var(--t3);margin-bottom:5px}
.cbar-row strong{color:var(--t2)}
.track{height:4px;background:var(--surf);border-radius:2px;overflow:hidden}
.fill{height:100%;border-radius:2px;background:linear-gradient(90deg,var(--gold),var(--grn));transition:width .6s ease}
.reasons{margin-top:13px;border-top:1px solid var(--brd);padding-top:11px;display:flex;flex-direction:column;gap:4px}
.ri{font-size:11px;color:var(--t2);display:flex;align-items:center;gap:5px}
.ri::before{content:'›';color:var(--gold);font-weight:700}
.nm{text-align:center;padding:28px 0;color:var(--t3);font-size:13px}
.nm .ni{font-size:26px;margin-bottom:7px}
.bot-grid{display:grid;grid-template-columns:1fr 310px;gap:14px}
.hcard{background:var(--card);border:1px solid var(--brd);border-radius:var(--r3);overflow:hidden}
.ch{padding:14px 18px;border-bottom:1px solid var(--brd);display:flex;align-items:center;justify-content:space-between}
.ct{font-size:13px;font-weight:600;color:var(--t1)}
.rbtn{background:none;border:1px solid var(--brd);border-radius:5px;padding:4px 9px;font-size:11px;color:var(--t2);cursor:pointer;font-family:'Inter',sans-serif;transition:border-color .15s,color .15s}
.rbtn:hover{border-color:var(--gold);color:var(--gold)}
table{width:100%;border-collapse:collapse}
thead th{padding:9px 14px;text-align:left;font-size:10px;font-weight:600;color:var(--t3);letter-spacing:.8px;text-transform:uppercase;background:var(--surf);border-bottom:1px solid var(--brd)}
tbody tr{border-bottom:1px solid var(--brd);transition:background .12s}
tbody tr:hover{background:var(--surf)}
tbody tr:last-child{border-bottom:none}
tbody td{padding:10px 14px;font-size:12px;color:var(--t2)}
.dt{display:inline-block;padding:2px 7px;border-radius:3px;font-size:11px;font-weight:700;font-family:'JetBrains Mono',monospace}
.dt-buy{background:var(--grnd);color:var(--grn)}.dt-sell{background:var(--redd);color:var(--red)}
.ot{display:inline-block;padding:2px 6px;border-radius:3px;font-size:10px;font-weight:600}
.oW{background:var(--grnd);color:var(--grn)}.oL{background:var(--redd);color:var(--red)}.oP{background:var(--card2);color:var(--t3)}
.mono{font-family:'JetBrains Mono',monospace}
.empty{padding:36px;text-align:center;color:var(--t3);font-size:13px}
.chart-card{background:var(--card);border:1px solid var(--brd);border-radius:var(--r3);overflow:hidden}
.chart-inner{padding:18px;display:flex;flex-direction:column;gap:18px}
.dw{position:relative;width:150px;height:150px;margin:0 auto}
.dc{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;pointer-events:none}
.dc .big{font-size:22px;font-weight:700;color:var(--t1);font-family:'JetBrains Mono',monospace;line-height:1}
.dc .small{font-size:10px;color:var(--t3);margin-top:3px}
hr.div{border:none;border-top:1px solid var(--brd)}
.legend{display:flex;flex-direction:column;gap:9px}
.lr{display:flex;align-items:center;justify-content:space-between}
.ll{display:flex;align-items:center;gap:7px;font-size:12px;color:var(--t2)}
.ldot{width:8px;height:8px;border-radius:2px;flex-shrink:0}
.lv{font-size:13px;font-weight:600;color:var(--t1);font-family:'JetBrains Mono',monospace}
.rrow{display:flex;align-items:center;justify-content:flex-end;gap:7px;margin-bottom:8px;font-size:11px;color:var(--t3)}
.ctrack{width:70px;height:2px;background:var(--brd);border-radius:1px;overflow:hidden}
.cfill{height:100%;background:var(--gold);border-radius:1px;width:100%;transition:width 1s linear}
.spin{width:18px;height:18px;border:2px solid var(--brd);border-top-color:var(--gold);border-radius:50%;animation:sp .7s linear infinite;display:inline-block}
@keyframes sp{to{transform:rotate(360deg)}}
#toast{position:fixed;bottom:20px;right:20px;background:var(--card2);border:1px solid var(--brd2);border-radius:var(--r2);padding:11px 16px;font-size:12px;color:var(--t1);z-index:999;opacity:0;transform:translateY(10px);transition:opacity .25s,transform .25s;pointer-events:none}
#toast.show{opacity:1;transform:translateY(0)}
@media(max-width:880px){.stats{grid-template-columns:repeat(2,1fr)}.sig-grid{grid-template-columns:1fr}.bot-grid{grid-template-columns:1fr}.tickers{display:none}}
@media(max-width:480px){main{padding:14px 12px 40px}.prices{grid-template-columns:1fr 1fr}}
</style>
</head>
<body>
<header>
  <div class="logo">
    <div class="logo-mark">📊</div>
    <span class="logo-text">Forex<span>Signal</span> Pro</span>
  </div>
  <div class="tickers">
    <div class="ticker"><span class="t-sym">XAU/USD</span><span class="t-price" id="htG">—</span><span class="t-chg" id="htGc" style="color:var(--t3)">—</span></div>
    <div class="ticker"><span class="t-sym">EUR/USD</span><span class="t-price" id="htE">—</span><span class="t-chg" id="htEc" style="color:var(--t3)">—</span></div>
  </div>
  <div class="live-badge"><div class="dot"></div>LIVE</div>
</header>

<main>
  <div class="lbl">Performance</div>
  <div class="stats">
    <div class="sc"><div class="sl">Total Signals</div><div class="sv" id="sTotal">—</div><div class="ss">All time</div></div>
    <div class="sc"><div class="sl">Win Rate</div><div class="sv" id="sWR" style="color:var(--grn)">—</div><div class="ss">Closed trades</div></div>
    <div class="sc"><div class="sl">Avg Pips</div><div class="sv" id="sPips" style="color:var(--blue)">—</div><div class="ss">Per trade</div></div>
    <div class="sc"><div class="sl">Losses</div><div class="sv" id="sLoss" style="color:var(--red)">—</div><div class="ss">All time</div></div>
  </div>

  <div class="rrow"><span id="rLabel">Refreshing in 30s</span><div class="ctrack"><div class="cfill" id="cFill"></div></div></div>

  <div class="lbl">Live Signal Analysis</div>
  <div class="sig-grid" id="sigGrid">
    <div style="display:flex;align-items:center;justify-content:center;height:160px"><div class="spin"></div></div>
    <div style="display:flex;align-items:center;justify-content:center;height:160px"><div class="spin"></div></div>
  </div>

  <div class="bot-grid">
    <div class="hcard">
      <div class="ch"><span class="ct">Signal History</span><button class="rbtn" onclick="loadAll()">↻ Refresh</button></div>
      <div id="histBody"><div class="empty">Loading…</div></div>
    </div>
    <div class="chart-card">
      <div class="ch"><span class="ct">Win Rate</span></div>
      <div class="chart-inner">
        <div class="dw"><canvas id="dChart"></canvas><div class="dc"><span class="big" id="dLabel">—</span><span class="small">Win rate</span></div></div>
        <hr class="div">
        <div class="legend">
          <div class="lr"><div class="ll"><div class="ldot" style="background:var(--grn)"></div>Wins</div><div class="lv" id="lW">—</div></div>
          <div class="lr"><div class="ll"><div class="ldot" style="background:var(--red)"></div>Losses</div><div class="lv" id="lL">—</div></div>
          <div class="lr"><div class="ll"><div class="ldot" style="background:var(--t3)"></div>Pending</div><div class="lv" id="lP">—</div></div>
        </div>
      </div>
    </div>
  </div>
</main>
<div id="toast"></div>

<script>
const REFRESH = 30;
let donut = null, cd = REFRESH, prev = {};

function fmt(v,d=2){ return v==null||isNaN(v)?'—':parseFloat(v).toFixed(d); }
function toast(m){ const e=document.getElementById('toast'); e.textContent=m; e.classList.add('show'); setTimeout(()=>e.classList.remove('show'),2600); }

async function api(path, fallback){
  try{
    const r = await fetch(path,{signal:AbortSignal.timeout(8000)});
    if(!r.ok) throw new Error(r.status);
    return await r.json();
  }catch{ return fallback; }
}

function renderStats(s){
  document.getElementById('sTotal').textContent = s.total??'—';
  document.getElementById('sWR').textContent    = (s.win_rate??'—')+'%';
  document.getElementById('sPips').textContent  = s.avg_pips>=0?'+'+s.avg_pips:s.avg_pips;
  document.getElementById('sLoss').textContent  = s.losses??'—';
}

function renderDonut(s){
  const p = Math.max(0, s.total - s.wins - s.losses);
  document.getElementById('dLabel').textContent = s.win_rate+'%';
  document.getElementById('lW').textContent = s.wins;
  document.getElementById('lL').textContent = s.losses;
  document.getElementById('lP').textContent = p;
  const data = {datasets:[{data:[s.wins,s.losses,p],backgroundColor:['#0ECB81','#F6465D','#243550'],borderColor:'transparent',borderWidth:0}]};
  if(donut){ donut.data=data; donut.update('none'); }
  else donut = new Chart(document.getElementById('dChart'),{type:'doughnut',data,options:{cutout:'72%',plugins:{legend:{display:false}},animation:{duration:500}}});
}

function buildCard(sig){
  if(!sig||sig.direction==='NEUTRAL'||!sig.entry){
    const sym=sig?sig.symbol:'—';
    const lbl=sym==='XAUUSD'?'GOLD (XAU/USD)':'EUR/USD';
    return `<div class="sig-card neutral">
      <div class="sc-top"><div class="sc-sym">${lbl}<small>${sym}</small></div><div class="badge b-neutral">NEUTRAL</div></div>
      <div class="nm"><div class="ni">📊</div>No confluence signal — awaiting next scan.</div></div>`;
  }
  const{symbol:sym,direction:dir,entry,sl,tp1,tp2,rr,confluence_score:cs,max_factors:mf,confidence:conf,reasons:rs=[]}=sig;
  const lbl=sym==='XAUUSD'?'GOLD (XAU/USD)':'EUR/USD';
  const dc=sym==='XAUUSD'?2:5;
  const cls=dir==='BUY'?'buy':'sell';
  const bcls=dir==='BUY'?'b-buy':'b-sell';
  const pct=Math.round((cs/(mf||5))*100);
  const rea=rs.map(r=>`<div class="ri">${r}</div>`).join('');
  return `<div class="sig-card ${cls}">
    <div class="sc-top"><div class="sc-sym">${lbl}<small>${sym}</small></div><div class="badge ${bcls}">${dir} ${dir==='BUY'?'↑':'↓'}</div></div>
    <div class="prices">
      <div class="pb entry"><div class="pb-l">Entry</div><div class="pb-v">${fmt(entry,dc)}</div></div>
      <div class="pb tp"><div class="pb-l">TP 1</div><div class="pb-v">${fmt(tp1,dc)}</div></div>
      <div class="pb sl"><div class="pb-l">Stop Loss</div><div class="pb-v">${fmt(sl,dc)}</div></div>
    </div>
    <div class="chips">
      <span class="chip">R:R 1:${rr}</span>
      <span class="chip">M15/H1</span>
      <span class="chip gold">${conf}</span>
      <span class="chip">TP2: ${fmt(tp2,dc)}</span>
    </div>
    <div class="cbar">
      <div class="cbar-row"><span>Confluence</span><strong>${cs}/${mf||5} factors</strong></div>
      <div class="track"><div class="fill" style="width:${pct}%"></div></div>
    </div>
    ${rea?`<div class="reasons">${rea}</div>`:''}
  </div>`;
}

function renderLive(data){
  document.getElementById('sigGrid').innerHTML =
    ['XAUUSD','EURUSD'].map(s=>buildCard(data[s])).join('');
}

function renderHistory(sigs){
  const b=document.getElementById('histBody');
  if(!sigs||!sigs.length){ b.innerHTML='<div class="empty">No signals yet.</div>'; return; }
  const rows=sigs.map(s=>{
    const lbl=s.symbol==='XAUUSD'?'🥇 GOLD':'💶 EUR/USD';
    const dc=s.symbol==='XAUUSD'?2:5;
    const dt=`<span class="dt dt-${s.direction.toLowerCase()}">${s.direction}</span>`;
    const oc=s.outcome==='WIN'?'oW':s.outcome==='LOSS'?'oL':'oP';
    const ot=`<span class="ot ${oc}">${s.outcome}</span>`;
    const ts=(s.timestamp||'').slice(0,16).replace('T',' ');
    return `<tr><td style="color:var(--t1);font-weight:500">${lbl}</td><td>${dt}</td>
      <td class="mono">${fmt(s.entry_price,dc)}</td>
      <td class="mono" style="color:var(--grn)">${fmt(s.tp1,dc)}</td>
      <td class="mono" style="color:var(--red)">${fmt(s.sl,dc)}</td>
      <td>${ot}</td><td style="color:var(--t3);font-size:11px">${ts}</td></tr>`;
  }).join('');
  b.innerHTML=`<table><thead><tr><th>Symbol</th><th>Dir</th><th>Entry</th><th>TP1</th><th>SL</th><th>Result</th><th>Time</th></tr></thead><tbody>${rows}</tbody></table>`;
}

function updateTickers(prices){
  ['XAUUSD','EURUSD'].forEach(s=>{
    const p=prices[s]; if(!p) return;
    const dc=s==='XAUUSD'?2:5;
    const ep=document.getElementById(s==='XAUUSD'?'htG':'htE');
    const ec=document.getElementById(s==='XAUUSD'?'htGc':'htEc');
    if(ep) ep.textContent=fmt(p,dc);
    if(ec&&prev[s]){
      const d=p-prev[s], pc=((d/prev[s])*100).toFixed(2);
      ec.textContent=(d>=0?'+':'')+pc+'%';
      ec.style.color=d>=0?'var(--grn)':'var(--red)';
    }
    prev[s]=p;
  });
}

function startCountdown(){
  cd=REFRESH;
  const f=document.getElementById('cFill'), l=document.getElementById('rLabel');
  const iv=setInterval(()=>{ cd--; if(f) f.style.width=((cd/REFRESH)*100)+'%'; if(l) l.textContent=`Refreshing in ${cd}s`; if(cd<=0) clearInterval(iv); },1000);
}

async function loadAll(){
  const [stats,live,hist,prices] = await Promise.all([
    api('/api/stats',   {total:0,wins:0,losses:0,win_rate:0,avg_pips:0}),
    api('/api/live',    {XAUUSD:{symbol:'XAUUSD',direction:'NEUTRAL'},EURUSD:{symbol:'EURUSD',direction:'NEUTRAL'}}),
    api('/api/signals', []),
    api('/api/prices',  {XAUUSD:0,EURUSD:0}),
  ]);
  renderStats(stats);
  renderDonut(stats);
  renderLive(live);
  renderHistory(hist);
  updateTickers(prices);
  startCountdown();
  toast('Data refreshed ✓');
}

loadAll();
setInterval(loadAll, REFRESH * 1000);
</script>
</body>
</html>"""

@app.route("/")
def index():
    return render_template_string(DASHBOARD_HTML)

# ── BOOT ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    init_db()
    logging.info(f"🌐 Dashboard → http://0.0.0.0:{PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=False)
