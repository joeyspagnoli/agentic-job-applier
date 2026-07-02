"""Self-contained HTML page templates for the digest subscription system.

Each public function returns a complete HTML document string.  Pages share
CSS design tokens and component classes extracted from the original React
signup bundle so they look visually identical without a build step.
"""

from __future__ import annotations

import html as _html

# ---------------------------------------------------------------------------
# Shared CSS — design tokens + component classes
# ---------------------------------------------------------------------------

_SHARED_CSS = """\
@import url("https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400;500;600;700&family=Newsreader:ital,wght@0,400;0,500;1,400&display=swap");

*,*::before,*::after{box-sizing:border-box;margin:0}

:root{
  --font-body:"Instrument Sans",-apple-system,system-ui,sans-serif;
  --font-display:"Newsreader",Georgia,serif;
  --ink:#1a1a1a;--ink-2:#4a4a4a;--ink-3:#777;--ink-4:#aaa;
  --surface:#fafaf9;--surface-raised:#fff;
  --line:#e5e4e1;
  --tint:#2c52a0;--tint-soft:#eef2fa;
  --danger:#c23;--danger-soft:#fef0f0;
  --success:#1a7f37;--success-soft:#dafbe1;
}

body{
  font-family:var(--font-body);background:var(--surface);color:var(--ink);
  -webkit-font-smoothing:antialiased;font-size:15px;line-height:1.5;margin:0;
}

.page{max-width:680px;margin:0 auto;padding:3rem 1.25rem 2rem;box-sizing:border-box}

.hdr{margin-bottom:1.75rem}
.hdr h1{font-family:var(--font-display);letter-spacing:-.01em;margin-bottom:.5rem;font-size:1.65rem;font-weight:500;line-height:1.2}
.hdr .desc{color:var(--ink-2);font-size:.92rem;line-height:1.55}
.hdr .desc strong{color:var(--ink);font-weight:600}

.form{background:var(--surface-raised);border:1px solid var(--line);border-radius:6px;padding:1.25rem;box-sizing:border-box}
.form-grid{display:grid;gap:1.5rem}
.row-2{display:grid;grid-template-columns:1fr 1fr;gap:.75rem}

.fld{display:flex;flex-direction:column;gap:.3rem}
.fld-label{color:var(--ink);letter-spacing:.01em;font-size:.78rem;font-weight:600}
.fld-opt{color:var(--ink-3);font-weight:400}
.fld input[type=text],.fld input[type=email]{
  font-family:var(--font-body);border:1px solid var(--line);background:var(--surface);
  color:var(--ink);border-radius:4px;outline:none;padding:.45rem .6rem;font-size:.88rem;
  transition:border-color .12s;width:100%;box-sizing:border-box;
}
.fld input:focus{border-color:var(--tint);box-shadow:0 0 0 2px var(--tint-soft)}
.fld input::placeholder{color:var(--ink-4)}
.fld input[readonly]{background:var(--surface);color:var(--ink-3);cursor:default}

.fld-row{display:flex;align-items:center;gap:.2rem}
.fld-row-label{min-width:5rem;flex-shrink:0;color:var(--ink);font-size:.78rem;font-weight:600}

.radios{display:flex;gap:.85rem}
.rad{cursor:pointer;display:flex;align-items:center;gap:.3rem}
.rad input[type=radio]{
  appearance:none;-webkit-appearance:none;border:1.5px solid var(--ink-4);cursor:pointer;
  border-radius:50%;width:14px;height:14px;margin:0;transition:border-color .1s;position:relative;
}
.rad input[type=radio]:checked{border-color:var(--tint)}
.rad input[type=radio]:checked::after{
  content:"";background:var(--tint);border-radius:50%;width:7px;height:7px;
  position:absolute;top:2.5px;left:2.5px;
}
.rad span{color:var(--ink-2);user-select:none;font-size:.85rem}

.chips-row{display:flex;align-items:baseline;gap:.2rem;overflow:hidden}
.chips-label{min-width:5rem;flex-shrink:0;padding-top:.2rem;color:var(--ink);font-size:.78rem;font-weight:600}
.chips-wrap{display:flex;flex-wrap:wrap;flex:1;gap:.35rem}
.chip{
  font-family:var(--font-body);color:var(--ink-2);background:var(--surface);
  border:1px solid var(--line);cursor:pointer;user-select:none;border-radius:3px;
  padding:.25rem .55rem;font-size:.78rem;font-weight:500;line-height:1.4;transition:all .1s;
}
.chip:hover{border-color:var(--ink-4)}
.chip[data-on="true"]{background:var(--tint-soft);color:var(--tint);border-color:#b8c9ea}
.chip-toggle{
  font-family:var(--font-body);color:var(--tint);cursor:pointer;background:0 0;border:none;
  flex-shrink:0;margin-left:.25rem;padding:.25rem 0;font-size:.7rem;font-weight:500;
}
.chip-toggle:hover{text-decoration:underline}

.exclude-ta{
  font-family:var(--font-body);border:1px solid var(--line);background:var(--surface);
  color:var(--ink);resize:vertical;border-radius:4px;outline:none;padding:.45rem .6rem;
  font-size:.85rem;line-height:1.5;transition:border-color .12s;width:100%;box-sizing:border-box;
}
.exclude-ta:focus{border-color:var(--tint);box-shadow:0 0 0 2px var(--tint-soft)}
.exclude-ta::placeholder{color:var(--ink-4)}

.sep{border:none;border-top:1px solid var(--line);margin:.25rem 0}

.submit-btn{
  cursor:pointer;width:100%;transition:background .12s;
  font-family:var(--font-body)!important;color:#fff!important;background:var(--tint)!important;
  border:none!important;border-radius:4px!important;padding:.55rem!important;
  font-size:.88rem!important;font-weight:600!important;
}
.submit-btn:hover:not(:disabled){background:#243f80!important}
.submit-btn:disabled{opacity:.55;cursor:default}

.danger-btn{
  cursor:pointer;width:100%;transition:background .12s;
  font-family:var(--font-body);color:var(--danger);background:var(--danger-soft);
  border:1px solid #f5d5d5;border-radius:4px;padding:.55rem;
  font-size:.85rem;font-weight:600;
}
.danger-btn:hover:not(:disabled){background:#fde0e0}
.danger-btn:disabled{opacity:.55;cursor:default}

.form-error{color:var(--danger);background:var(--danger-soft);border:1px solid #f5d5d5;border-radius:4px;padding:.4rem .6rem;font-size:.8rem}
.form-success{color:var(--success);background:var(--success-soft);border:1px solid #b4dfbe;border-radius:4px;padding:.4rem .6rem;font-size:.8rem}

.fine{color:var(--ink-3);text-align:center;font-size:.72rem;line-height:1.5}

.confirm-page{text-align:center;max-width:400px;margin:6rem auto;padding:0 1.25rem}
.confirm-page h2{font-family:var(--font-display);margin-bottom:.5rem;font-size:1.3rem;font-weight:500}
.confirm-page p{color:var(--ink-2);font-size:.92rem;line-height:1.6}
.confirm-page strong{color:var(--ink)}
.confirm-page a{color:var(--tint);text-decoration:underline;text-underline-offset:2px}
.confirm-page a:hover{color:#243f80}

.foot{border-top:1px solid var(--line);margin-top:1.5rem;padding-top:1rem}
.foot p{color:var(--ink-3);font-size:.72rem;line-height:1.7}
.foot p+p{margin-top:.15rem}
.foot a{color:var(--ink-2);text-underline-offset:2px;text-decoration:underline}
.foot a:hover{color:var(--ink)}

.hidden-companies{display:flex;flex-wrap:wrap;gap:.35rem;margin-top:.3rem}
.hidden-co{
  display:inline-flex;align-items:center;gap:.3rem;
  background:var(--surface);border:1px solid var(--line);border-radius:3px;
  padding:.2rem .45rem;font-size:.78rem;color:var(--ink-2);
}
.hidden-co button{
  background:none;border:none;cursor:pointer;color:var(--ink-4);
  font-size:.85rem;line-height:1;padding:0 0 0 .15rem;transition:color .1s;
}
.hidden-co button:hover{color:var(--danger)}

.toast{
  position:fixed;top:1rem;left:50%;transform:translateX(-50%);
  padding:.5rem 1rem;border-radius:4px;font-size:.85rem;font-weight:500;
  opacity:0;transition:opacity .3s;pointer-events:none;z-index:100;
}
.toast.show{opacity:1}
.toast.success{background:var(--success-soft);color:var(--success);border:1px solid #b4dfbe}
.toast.error{background:var(--danger-soft);color:var(--danger);border:1px solid #f5d5d5}

.loading{text-align:center;color:var(--ink-3);padding:3rem 0;font-size:.9rem}
"""

_FOOTER_HTML = """\
<footer class="foot">
  <p>
    Built by
    <a href="https://linkedin.com/in/joseph-spagnoli" target="_blank" rel="noopener noreferrer">Joey Spagnoli</a>
    &middot; Powered by
    <a href="https://github.com/joeyspagnoli/agentic-job-applier" target="_blank" rel="noopener noreferrer">agentic-job-applier</a>
  </p>
  <p>
    Direct scrapers for Greenhouse, Workday, Lever, LinkedIn &amp; more
    &middot; Community data via
    <a href="https://github.com/SimplifyJobs/Summer2026-Internships" target="_blank" rel="noopener noreferrer">SimplifyJobs</a>
    &amp;
    <a href="https://github.com/vanshb03/Summer2027-Internships" target="_blank" rel="noopener noreferrer">vanshb03</a>
  </p>
</footer>"""


def _base_html(title: str, body: str, extra_head: str = "") -> str:
    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{_html.escape(title)}</title>
  <link rel="icon" type="image/png" href="/favicon.png">
  <link rel="icon" type="image/x-icon" href="/favicon.ico">
  <link rel="apple-touch-icon" href="/apple-touch-icon.png">
  <style>{_SHARED_CSS}</style>
  {extra_head}
</head>
<body>
{body}
</body>
</html>"""


# ---------------------------------------------------------------------------
# Subscribe page
# ---------------------------------------------------------------------------

def subscribe_page(turnstile_site_key: str) -> str:
    """Return the full signup form page as a self-contained HTML string."""
    escaped_key = _html.escape(turnstile_site_key, quote=True)
    body = f"""\
<div class="page">
  <header class="hdr">
    <h1>Joey's CS Job Digest</h1>
    <p class="desc">
      <strong>Daily at 3 pm EST.</strong> Internship &amp; new-grad roles from
      2,800+ companies, scraped directly from career pages and community trackers.
      Hide companies you don't want right from the email.
    </p>
  </header>

  <form id="signup-form" class="form" novalidate>
    <div class="form-grid">
      <div class="row-2">
        <div class="fld">
          <label class="fld-label" for="name">Name</label>
          <input id="name" type="text" placeholder="Your name" required>
        </div>
        <div class="fld">
          <label class="fld-label" for="email">Email</label>
          <input id="email" type="email" placeholder="you@example.com" required>
        </div>
      </div>

      <hr class="sep">

      <div class="fld-row">
        <span class="fld-row-label">Role</span>
        <div class="radios">
          <label class="rad"><input type="radio" name="role" value="intern"><span>Intern</span></label>
          <label class="rad"><input type="radio" name="role" value="new_grad"><span>New Grad</span></label>
          <label class="rad"><input type="radio" name="role" value="both"><span>Both</span></label>
        </div>
      </div>

      <div class="chips-row">
        <span class="chips-label">Fields</span>
        <div class="chips-wrap" id="chips">
          <button type="button" class="chip" data-on="false" data-id="software">Software Eng</button>
          <button type="button" class="chip" data-on="false" data-id="ai_ml_data">AI / ML / Data</button>
          <button type="button" class="chip" data-on="false" data-id="hardware">Hardware</button>
          <button type="button" class="chip" data-on="false" data-id="product">Product</button>
          <button type="button" class="chip" data-on="false" data-id="quant">Quant</button>
        </div>
        <button type="button" class="chip-toggle" id="chip-toggle">select all</button>
      </div>

      <div class="chips-row">
        <span class="chips-label">Terms</span>
        <div class="chips-wrap" id="term-chips">
          <button type="button" class="chip" data-on="false" data-id="Fall 2026">Fall 26</button>
          <button type="button" class="chip" data-on="false" data-id="Spring 2027">Spring 27</button>
          <button type="button" class="chip" data-on="false" data-id="Summer 2027">Summer 27</button>
        </div>
        <button type="button" class="chip-toggle" id="term-toggle">select all</button>
      </div>

      <div class="fld-row">
        <span class="fld-row-label">Location</span>
        <div class="radios">
          <label class="rad"><input type="radio" name="location" value="remote"><span>Remote</span></label>
          <label class="rad"><input type="radio" name="location" value="both"><span>Either</span></label>
          <label class="rad"><input type="radio" name="location" value="in_person"><span>On-site</span></label>
        </div>
      </div>

      <div class="fld">
        <label class="fld-label" for="exclude">
          Exclude companies <span class="fld-opt">(optional, one per line)</span>
        </label>
        <textarea id="exclude" class="exclude-ta" rows="3" placeholder="Amazon&#10;Meta&#10;Oracle"></textarea>
      </div>

      <hr class="sep">

      <div class="cf-turnstile" data-sitekey="{escaped_key}"></div>

      <p id="form-error" class="form-error" style="display:none"></p>

      <button type="submit" id="submit-btn" class="submit-btn">Subscribe</button>

      <p class="fine">
        Confirmation email required. Hide any company directly from the digest.
      </p>
    </div>
  </form>

  <div id="confirm-msg" class="confirm-page" style="display:none">
    <h2>Check your email</h2>
    <p>
      We sent a confirmation link to <strong id="confirm-email"></strong>.
      Click it to start receiving your daily digest at 3 pm EST.
    </p>
  </div>

  {_FOOTER_HTML}
</div>

<script src="https://challenges.cloudflare.com/turnstile/v0/api.js" async defer></script>
<script>
(function(){{
  var form=document.getElementById('signup-form');
  var errEl=document.getElementById('form-error');
  var btn=document.getElementById('submit-btn');
  var chips=document.querySelectorAll('#chips .chip');
  var toggle=document.getElementById('chip-toggle');
  var selectedFields=new Set();
  var termChips=document.querySelectorAll('#term-chips .chip');
  var termToggle=document.getElementById('term-toggle');
  var selectedTerms=new Set();

  function bindChipGroup(chipEls,toggleEl,selectedSet){{
    chipEls.forEach(function(c){{
      c.addEventListener('click',function(){{
        var id=c.dataset.id;
        if(selectedSet.has(id)){{selectedSet.delete(id);c.dataset.on='false';}}
        else{{selectedSet.add(id);c.dataset.on='true';}}
        toggleEl.textContent=selectedSet.size===chipEls.length?'clear all':'select all';
      }});
    }});
    toggleEl.addEventListener('click',function(){{
      if(selectedSet.size===chipEls.length){{
        selectedSet.clear();
        chipEls.forEach(function(c){{c.dataset.on='false';}});
      }}else{{
        chipEls.forEach(function(c){{selectedSet.add(c.dataset.id);c.dataset.on='true';}});
      }}
      toggleEl.textContent=selectedSet.size===chipEls.length?'clear all':'select all';
    }});
  }}
  bindChipGroup(chips,toggle,selectedFields);
  bindChipGroup(termChips,termToggle,selectedTerms);

  function showError(msg){{errEl.textContent=msg;errEl.style.display='block';}}
  function hideError(){{errEl.style.display='none';}}

  form.addEventListener('submit',function(e){{
    e.preventDefault();hideError();
    var name=document.getElementById('name').value.trim();
    var email=document.getElementById('email').value.trim();
    var role=document.querySelector('input[name=role]:checked');
    var loc=document.querySelector('input[name=location]:checked');
    if(!name||!email||!role||selectedFields.size===0||selectedTerms.size===0||!loc){{
      showError('Fill out all fields, pick at least one area of interest, and select at least one term.');return;
    }}
    btn.disabled=true;btn.textContent='Subscribing…';
    var excluded=document.getElementById('exclude').value.split('\\n').map(function(s){{return s.trim();}}).filter(Boolean);
    var token='';
    try{{token=window.turnstile&&window.turnstile.getResponse()||'';}}catch(ex){{}}
    fetch('/api/digest/subscribe',{{
      method:'POST',headers:{{'Content-Type':'application/json'}},
      body:JSON.stringify({{
        name:name,email:email,role_level:role.value,
        fields:Array.from(selectedFields),terms:Array.from(selectedTerms),
        location_preference:loc.value,
        excluded_companies:excluded,turnstile_token:token
      }})
    }}).then(function(r){{
      if(!r.ok)return r.json().then(function(d){{throw new Error(d.message||'Failed ('+r.status+')');}});
      return r.json();
    }}).then(function(){{
      form.style.display='none';
      var cm=document.getElementById('confirm-msg');
      document.getElementById('confirm-email').textContent=email;
      cm.style.display='block';
    }}).catch(function(err){{
      showError(err.message||'Something went wrong.');
      btn.disabled=false;btn.textContent='Subscribe';
    }});
  }});
}})();
</script>"""
    return _base_html("Joey's CS Job Digest", body)


# ---------------------------------------------------------------------------
# Manage preferences page
# ---------------------------------------------------------------------------

def manage_page() -> str:
    """Return the preferences management page as a self-contained HTML string."""
    body = f"""\
<div id="toast" class="toast"></div>

<div class="page">
  <header class="hdr">
    <h1>Joey's CS Job Digest</h1>
    <p class="desc">Manage your digest preferences.</p>
  </header>

  <div id="loading" class="loading">Loading your preferences&hellip;</div>
  <div id="error-page" class="confirm-page" style="display:none">
    <h2>Invalid link</h2>
    <p>This preferences link is invalid or has expired.</p>
  </div>

  <div id="prefs" style="display:none">
    <div class="form">
      <div class="form-grid">
        <div class="row-2">
          <div class="fld">
            <label class="fld-label">Name</label>
            <input id="p-name" type="text" readonly>
          </div>
          <div class="fld">
            <label class="fld-label">Email</label>
            <input id="p-email" type="email" readonly>
          </div>
        </div>

        <hr class="sep">

        <div class="fld-row">
          <span class="fld-row-label">Role</span>
          <div class="radios">
            <label class="rad"><input type="radio" name="role" value="intern"><span>Intern</span></label>
            <label class="rad"><input type="radio" name="role" value="new_grad"><span>New Grad</span></label>
            <label class="rad"><input type="radio" name="role" value="both"><span>Both</span></label>
          </div>
        </div>

        <div class="chips-row">
          <span class="chips-label">Fields</span>
          <div class="chips-wrap" id="chips">
            <button type="button" class="chip" data-on="false" data-id="software">Software Eng</button>
            <button type="button" class="chip" data-on="false" data-id="ai_ml_data">AI / ML / Data</button>
            <button type="button" class="chip" data-on="false" data-id="hardware">Hardware</button>
            <button type="button" class="chip" data-on="false" data-id="product">Product</button>
            <button type="button" class="chip" data-on="false" data-id="quant">Quant</button>
          </div>
          <button type="button" class="chip-toggle" id="chip-toggle">select all</button>
        </div>

        <div class="chips-row">
          <span class="chips-label">Terms</span>
          <div class="chips-wrap" id="term-chips">
            <button type="button" class="chip" data-on="false" data-id="Fall 2026">Fall 26</button>
            <button type="button" class="chip" data-on="false" data-id="Spring 2027">Spring 27</button>
            <button type="button" class="chip" data-on="false" data-id="Summer 2027">Summer 27</button>
          </div>
          <button type="button" class="chip-toggle" id="term-toggle">select all</button>
        </div>

        <div class="fld-row">
          <span class="fld-row-label">Location</span>
          <div class="radios">
            <label class="rad"><input type="radio" name="location" value="remote"><span>Remote</span></label>
            <label class="rad"><input type="radio" name="location" value="both"><span>Either</span></label>
            <label class="rad"><input type="radio" name="location" value="in_person"><span>On-site</span></label>
          </div>
        </div>

        <hr class="sep">

        <div class="fld">
          <label class="fld-label">Hidden companies</label>
          <div id="hidden-list" class="hidden-companies"></div>
          <p id="no-hidden" style="color:var(--ink-4);font-size:.8rem;margin-top:.3rem">
            No companies hidden yet. Use the "hide" link in your digest email, or add below.
          </p>
        </div>

        <div class="fld">
          <label class="fld-label" for="add-exclude">
            Add companies to hide <span class="fld-opt">(one per line)</span>
          </label>
          <textarea id="add-exclude" class="exclude-ta" rows="2" placeholder="Amazon&#10;Oracle"></textarea>
        </div>

        <hr class="sep">

        <button type="button" id="save-btn" class="submit-btn">Save preferences</button>

        <hr class="sep" style="margin-top:.5rem">

        <button type="button" id="unsub-btn" class="danger-btn">Unsubscribe from all emails</button>
      </div>
    </div>

    {_FOOTER_HTML}
  </div>

  <div id="unsub-done" class="confirm-page" style="display:none">
    <h2>Unsubscribed</h2>
    <p>You've been removed from the digest mailing list. You can re-subscribe any time at <a href="/subscribe">/subscribe</a>.</p>
  </div>
</div>

<script>
(function(){{
  var token=new URLSearchParams(window.location.search).get('token');
  if(!token){{
    document.getElementById('loading').style.display='none';
    document.getElementById('error-page').style.display='block';return;
  }}

  var selectedFields=new Set();
  var selectedTerms=new Set();
  var excludedCompanies=[];
  var chips=document.querySelectorAll('#chips .chip');
  var toggleBtn=document.getElementById('chip-toggle');
  var termChips=document.querySelectorAll('#term-chips .chip');
  var termToggle=document.getElementById('term-toggle');

  function bindChipGroup(chipEls,toggleEl,selectedSet){{
    chipEls.forEach(function(c){{
      c.addEventListener('click',function(){{
        var id=c.dataset.id;
        if(selectedSet.has(id)){{selectedSet.delete(id);c.dataset.on='false';}}
        else{{selectedSet.add(id);c.dataset.on='true';}}
        toggleEl.textContent=selectedSet.size===chipEls.length?'clear all':'select all';
      }});
    }});
    toggleEl.addEventListener('click',function(){{
      if(selectedSet.size===chipEls.length){{
        selectedSet.clear();
        chipEls.forEach(function(c){{c.dataset.on='false';}});
      }}else{{
        chipEls.forEach(function(c){{selectedSet.add(c.dataset.id);c.dataset.on='true';}});
      }}
      toggleEl.textContent=selectedSet.size===chipEls.length?'clear all':'select all';
    }});
  }}
  bindChipGroup(chips,toggleBtn,selectedFields);
  bindChipGroup(termChips,termToggle,selectedTerms);

  function showToast(msg,type){{
    var t=document.getElementById('toast');
    t.textContent=msg;t.className='toast '+type+' show';
    setTimeout(function(){{t.className='toast';}},3000);
  }}

  function renderHidden(){{
    var list=document.getElementById('hidden-list');
    var noMsg=document.getElementById('no-hidden');
    list.innerHTML='';
    if(excludedCompanies.length===0){{noMsg.style.display='block';return;}}
    noMsg.style.display='none';
    excludedCompanies.forEach(function(name,i){{
      var el=document.createElement('span');el.className='hidden-co';
      var textNode=document.createTextNode(name);
      var btn=document.createElement('button');btn.type='button';
      btn.textContent='\\u00d7';btn.title='Unhide '+name;
      btn.addEventListener('click',function(){{
        excludedCompanies.splice(i,1);renderHidden();
      }});
      el.appendChild(textNode);el.appendChild(btn);
      list.appendChild(el);
    }});
  }}

  fetch('/api/digest/preferences?token='+encodeURIComponent(token))
  .then(function(r){{
    if(!r.ok)throw new Error('not found');return r.json();
  }})
  .then(function(data){{
    document.getElementById('loading').style.display='none';
    document.getElementById('prefs').style.display='block';

    document.getElementById('p-name').value=data.name;
    document.getElementById('p-email').value=data.email;

    var roleRadio=document.querySelector('input[name=role][value="'+data.role_level+'"]');
    if(roleRadio)roleRadio.checked=true;

    (data.fields||[]).forEach(function(f){{
      selectedFields.add(f);
      var c=document.querySelector('#chips .chip[data-id="'+f+'"]');
      if(c)c.dataset.on='true';
    }});
    toggleBtn.textContent=selectedFields.size===chips.length?'clear all':'select all';

    (data.terms||[]).forEach(function(t){{
      selectedTerms.add(t);
      var c=document.querySelector('#term-chips .chip[data-id="'+t+'"]');
      if(c)c.dataset.on='true';
    }});
    termToggle.textContent=selectedTerms.size===termChips.length?'clear all':'select all';

    var locRadio=document.querySelector('input[name=location][value="'+data.location_preference+'"]');
    if(locRadio)locRadio.checked=true;

    excludedCompanies=(data.excluded_companies||[]).slice();
    renderHidden();
  }})
  .catch(function(){{
    document.getElementById('loading').style.display='none';
    document.getElementById('error-page').style.display='block';
  }});

  document.getElementById('save-btn').addEventListener('click',function(){{
    var btn=document.getElementById('save-btn');
    btn.disabled=true;btn.textContent='Saving…';

    var role=document.querySelector('input[name=role]:checked');
    var loc=document.querySelector('input[name=location]:checked');
    var addText=document.getElementById('add-exclude').value;
    var added=addText.split('\\n').map(function(s){{return s.trim();}}).filter(Boolean);
    added.forEach(function(c){{
      if(excludedCompanies.indexOf(c)===-1)excludedCompanies.push(c);
    }});

    fetch('/api/digest/preferences?token='+encodeURIComponent(token),{{
      method:'PUT',headers:{{'Content-Type':'application/json'}},
      body:JSON.stringify({{
        role_level:role?role.value:undefined,
        fields:Array.from(selectedFields),
        terms:Array.from(selectedTerms),
        location_preference:loc?loc.value:undefined,
        excluded_companies:excludedCompanies
      }})
    }}).then(function(r){{
      if(!r.ok)throw new Error('Save failed');
      document.getElementById('add-exclude').value='';
      renderHidden();
      showToast('Preferences saved','success');
    }}).catch(function(err){{
      showToast(err.message||'Something went wrong','error');
    }}).finally(function(){{
      btn.disabled=false;btn.textContent='Save preferences';
    }});
  }});

  document.getElementById('unsub-btn').addEventListener('click',function(){{
    if(!confirm('Are you sure you want to unsubscribe? You will stop receiving the daily digest.'))return;
    var btn=document.getElementById('unsub-btn');
    btn.disabled=true;btn.textContent='Unsubscribing…';

    fetch('/api/digest/unsubscribe?token='+encodeURIComponent(token),{{method:'DELETE'}})
    .then(function(r){{
      if(!r.ok)throw new Error('Failed');
      document.getElementById('prefs').style.display='none';
      document.getElementById('unsub-done').style.display='block';
    }}).catch(function(){{
      showToast('Something went wrong','error');
      btn.disabled=false;btn.textContent='Unsubscribe from all emails';
    }});
  }});
}})();
</script>"""
    return _base_html("Manage Preferences — Joey's CS Job Digest", body)


# ---------------------------------------------------------------------------
# Confirmation page (after clicking email confirm link)
# ---------------------------------------------------------------------------

def confirm_page(email: str) -> str:
    """Return a success page shown after a subscriber confirms via email link."""
    safe_email = _html.escape(email)
    body = f"""\
<div class="confirm-page">
  <h2>You're confirmed!</h2>
  <p>
    <strong>{safe_email}</strong> is now subscribed to Joey's CS Job Digest.
    Your first digest will arrive at 3 pm EST today (or tomorrow if it's already past 3 pm).
  </p>
  <p style="margin-top:1rem">
    <a href="/subscribe">Back to home</a>
  </p>
</div>"""
    return _base_html("Confirmed — Joey's CS Job Digest", body)


# ---------------------------------------------------------------------------
# Unsubscribe confirmation page
# ---------------------------------------------------------------------------

def unsubscribe_page() -> str:
    """Return the page shown after a subscriber unsubscribes."""
    body = """\
<div class="confirm-page">
  <h2>Unsubscribed</h2>
  <p>
    You've been removed from the digest mailing list.
    You can re-subscribe any time at <a href="/subscribe">/subscribe</a>.
  </p>
</div>"""
    return _base_html("Unsubscribed — Joey's CS Job Digest", body)


# ---------------------------------------------------------------------------
# Hide success page (after clicking "hide" on a company in the email)
# ---------------------------------------------------------------------------

def hide_success_page(company: str, manage_url: str) -> str:
    """Return the page shown after hiding a company from the digest."""
    safe_company = _html.escape(company)
    safe_url = _html.escape(manage_url, quote=True)
    body = f"""\
<div class="confirm-page">
  <h2>Company hidden</h2>
  <p>
    You won't see jobs from <strong>{safe_company}</strong> in future digests.
  </p>
  <p style="margin-top:1rem">
    <a href="{safe_url}">Manage all preferences</a>
  </p>
</div>"""
    return _base_html("Hidden — Joey's CS Job Digest", body)
