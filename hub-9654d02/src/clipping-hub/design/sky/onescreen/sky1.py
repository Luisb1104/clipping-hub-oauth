import json, os
D = os.path.dirname(os.path.abspath(__file__))
TOK = open(D + '/../sky-air-tokens.css').read()
CSS = open(D + '/../sky.css').read()
I = {
 'ov': '<svg viewBox="0 0 24 24"><rect x="4" y="4" width="7" height="7" rx="2"/><rect x="13" y="4" width="7" height="7" rx="2"/><rect x="4" y="13" width="7" height="7" rx="2"/><rect x="13" y="13" width="7" height="7" rx="2"/></svg>',
 'q': '<svg viewBox="0 0 24 24"><path d="M5 7h14M5 12h14M5 17h9"/></svg>',
 'fl': '<svg viewBox="0 0 24 24"><path d="M6 21V4M6 5h11l-2 4 2 4H6"/></svg>',
 'co': '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="8"/><path d="M12 8v8M14.5 10H11a1.5 1.5 0 0 0 0 3h2a1.5 1.5 0 0 1 0 3H9.5"/></svg>',
 'ea': '<svg viewBox="0 0 24 24"><path d="M4 19h16M7 16v-5M12 16V7M17 16v-8"/></svg>',
 'ok': '<svg viewBox="0 0 24 24"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
 'ed': '<svg viewBox="0 0 24 24"><path d="M4 20l1-5L16 4l4 4L9 19z"/></svg>',
 'x': '<svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18"/></svg>',
 'lock': '<svg viewBox="0 0 24 24"><rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/></svg>',
 'play': '<svg class="pi" viewBox="0 0 24 24"><path d="M7 4l13 8-13 8z"/></svg>',
 'sun': '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>',
 'moon': '<svg viewBox="0 0 24 24"><path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/></svg>',
 'g_ring': '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="7"/></svg>',
 'g_sq': '<svg viewBox="0 0 24 24"><rect x="5" y="5" width="14" height="14" rx="4"/></svg>',
 'g_dia': '<svg viewBox="0 0 24 24"><path d="M12 3l9 9-9 9-9-9z"/></svg>',
 'g_tri': '<svg viewBox="0 0 24 24"><path d="M8 5l11 7-11 7z"/></svg>',
 'inbox': '<svg viewBox="0 0 24 24"><path d="M4 13l2-7h12l2 7v5H4zM4 13h5l1 2h4l1-2h5"/></svg>',
 'flag0': '<svg viewBox="0 0 24 24"><path d="M6 21V4M6 5h11l-2 4 2 4H6"/></svg>',
 'chart0': '<svg viewBox="0 0 24 24"><path d="M4 19h16M7 16v-5M12 16V7M17 16v-8"/></svg>',
}
TABS = [('ov', 'Overview'), ('q', 'Queue'), ('fl', 'Flags'), ('co', 'Costs'), ('ea', 'Earnings')]
MTABS = ['Overview', 'Queue / Approvals', 'Policy flags', 'Costs vs Earnings', 'Earnings']
STAMP_P = '<div class="stamp">EXAMPLE DATA · DRAFT MOCKUP · NOT LIVE<br>NO ACCOUNTS CONNECTED, BUTTONS DO NOTHING</div>'
STAMP_M = '<div class="stamp">EXAMPLE DATA · DRAFT MOCKUP · NOT LIVE · NO ACCOUNTS CONNECTED, BUTTONS DO NOTHING</div>'
INTENT = " The Light / Dark switch (top right) shows the design intent: follows device setting unless you choose. It is not a built feature."
CAPS = {
 'overview': ("Today's routine on one screen: example clips are ready for you, and which platforms are planned (YouTube first, the others later). Nothing is connected yet." + INTENT,
              "Resolve the open flags, then Approve all, or Review one by one. Approve = send to Postiz as a draft only. Nothing posts."),
 'queue': ("The batch of example clips waiting for your OK. Each shows a preview, where it would go, any open flag, and three buttons." + INTENT,
           "Fix flagged clips, then Approve, Edit or Reject each clip. Approve batch stays blocked until flags are resolved. Approve = draft only; nothing posts."),
 'flags': ("Example warnings about copyright and monetization, each with plain advice on what to do. All are EXAMPLE only." + INTENT,
           "Open a flagged clip, fix it, then come back. While any flag is open, Approve all and Approve batch stay blocked. Approve = draft only."),
 'costs': ("An example monthly cost next to earnings. The cost is an example, not a quote. Earnings show no data yet, with a hatched placeholder." + INTENT,
           "Read the example cost and the planned tools. Nothing here is billed or connected. Earnings stay empty until real data exists."),
 'earnings': ("Earnings pooled by platform. Whether each platform shares revenue data is Unverified, so every row says so. The bank check shows the concept only, with dashes." + INTENT,
              "Nothing to do yet. Later, you would compare what a platform says it paid with what lands in your bank."),
 'empty': ("What each area looks like before anything exists: no clips, no flags, no earnings data. These are example empty states." + INTENT,
           "Follow the next step on each card. Connecting a channel is the first step (buttons do nothing in this mockup)."),
 'connect': ("The four channel slots. All show Not connected, and YouTube carries a Planned · first hint. Icons are neutral shapes, not brand logos." + INTENT,
             "Later you would tap Connect on a channel. In this mockup the buttons do nothing, and nothing posts. Approve = draft only."),
 'mac-overview': ("The same Overview on a big screen: today's approval, example warnings, and an example cost next to earnings (no data yet)." + INTENT,
                  "Resolve open flags, approve the example clips, and check cost vs earnings. Approve = send to Postiz as a draft only; nothing posts."),
 'mac-more': ("Flags, Costs vs Earnings, Earnings and Connect channels together on one big screen. Everything is example data or empty." + INTENT,
              "Scan the example flags, the example cost, the Unverified earnings rows and the channel slots. Nothing is connected; buttons do nothing."),
}
def cap(k):
    a, b = CAPS[k]
    return f'<div class="cap"><p><b>What you\'re looking at:</b>{a}</p><p><b>What you do here:</b>{b}</p></div>'
def toggle(theme, lbl=False):
    on = lambda t: ' on' if theme == t else ''
    L = ' lbl' if lbl else ''
    return (f'<div class="tg{L}"><i class="{on("light").strip()}">{I["sun"]}' + ('Light' if lbl else '') + f'</i><i class="{on("dark").strip()}">{I["moon"]}' + ('Dark' if lbl else '') + '</i></div>')
def reel(): return '<div class="reel"><i>C</i><div><b>Clip helper (name TBD)</b><small>Planned helper</small></div></div>'
def hdr(theme): return f'<div class="hdr">{reel()}{toggle(theme)}</div>'
def nav(on):
    return '<div class="navC">' + ''.join(f'<a class="{"on" if i==on else ""}">{I[k]}<span>{n}</span></a>' for i, (k, n) in enumerate(TABS)) + '</div>'
def thumbs(): return ''.join(f'<div class="th th{i}">{I["play"]}<small>Example clip {i}</small></div>' for i in (1, 2, 3))
BLK = f'<div class="blk">{I["fl"]}Resolve open flags first</div>'
SAFE0 = f'<div class="safe">{I["lock"]}<span>Nothing posts until you approve (draft only)<small>Approve = send to Postiz as a draft only</small></span></div>'
SAFE = BLK + SAFE0
PWR = '<div class="pwr">Planned tools (not connected): OpusClip · Postiz · TubeAlfred · Remotion</div>'
FLC = {2: '<span class="chip warn dash">Flag · music (EXAMPLE)</span>', 3: '<span class="chip bad dash">Flag · reuse (EXAMPLE)</span>'}
def chips(i=1): return '<span class="chip plan">YouTube · planned</span><span class="chip off">IG · FB · TikTok later</span>' + FLC.get(i, '')
def qbtns(i=1): return f'<div class="bt"><div class="btn {"pri" if i==1 else "dis"}">{I["ok"]}Approve</div><div class="btn gl">{I["ed"]}Edit</div><div class="btn rej">{I["x"]}Reject</div></div>'
MUSIC = ('Possible copyrighted music.', 'Remove it or replace it with a licensed track before approving. Rules differ by platform and account type.')
REUSE = ('Reused-content risk.', "YouTube may limit monetization of clips from someone else&rsquo;s video unless you add significant original commentary or edits. Your own footage is fine.")
def flag_card(kind, clip):
    t, b = MUSIC if kind == 'm' else REUSE
    chip = '<span class="chip warn dash">EXAMPLE · Amber</span>' if kind == 'm' else '<span class="chip bad dash">EXAMPLE · Rose</span>'
    n = 2 if kind == 'm' else 3
    return (f'<div class="glass card fcard"><div class="row">{chip}<span class="chip">Example clip {n}</span></div>'
            f'<h3>{t}</h3><p>{b}</p><div class="btn gl">{I["ed"]} Open clip to fix</div></div>')
def flag_rows():
    return ''.join(f'<div class="fl"><span class="chip {c} dash">EXAMPLE · {s}</span><div><b>{t}</b><span class="sub">{b}</span></div></div>' for c, s, (t, b) in (('warn', 'Amber', MUSIC), ('bad', 'Rose', REUSE)))
HATCH = lambda h: f'<div class="hatch" style="height:{h}px"></div>'
def cost_box():
    return '<div class="k">Costs · example</div><div class="big">Example: <span style="white-space:nowrap">~$30–75/month</span></div><div class="sub">Not a quote · tools to be confirmed</div>'
def earn_empty(h=110):
    return f'<div class="k">Earnings</div><div class="big" style="color:var(--text-2)">No data yet</div>{HATCH(h)}<div class="sub" style="margin-top:8px">Example shape only. No real revenue yet.</div>'
def plan_chips(): return '<div class="plc">' + ''.join(f'<span class="chip dash">{n}</span>' for n in ('OpusClip', 'Postiz', 'TubeAlfred', 'Remotion')) + '</div>'
PL = [('YouTube', 'g_tri'), ('TikTok', 'g_dia'), ('Instagram', 'g_ring'), ('Facebook', 'g_sq')]
def earn_rows():
    return ''.join(f'<div class="er"><div class="gl2">{I[g]}</div><div class="nm">{n}<span><span class="chip dash" style="font-size:11px;padding:3px 8px">Revenue data: Unverified</span></span></div><div class="va">$—</div></div>' for n, g in PL)
def bank():
    return ('<div class="bank"><div class="bx"><div class="k">Payout reported</div><div class="v">$—</div></div><div class="bx"><div class="k">Deposit found in bank</div><div class="v">$—</div></div></div>'
            f'<div class="pat"><span>Pattern A</span><span class="pp">$— = $—</span><span class="chip ok dash">EXAMPLE · Match</span></div>'
            f'<div class="pat"><span>Pattern B</span><span class="pp">$— ≠ $—</span><span class="chip bad dash">EXAMPLE · Mismatch</span></div>'
            '<div class="sub" style="margin-top:6px">Concept only: compares what a platform says it paid with what lands in your bank.</div>')
CH = [('Instagram', 'g_ring'), ('Facebook', 'g_sq'), ('TikTok', 'g_dia'), ('YouTube', 'g_tri')]
def slot(n, g):
    extra = '<span class="chip plan">Planned · first</span>' if n == 'YouTube' else ''
    return f'<div class="glass slot"><div class="gl2">{I[g]}</div><div class="nm">{n}<div class="chips"><span class="chip dash">Not connected</span>{extra}</div></div><div class="btn gl">Connect</div></div>'
def empty_card(ic, title, body, btn, pri=False):
    return f'<div class="glass card empty"><div class="ic">{I[ic]}</div><h3>{title}</h3><p>{body}</p><div class="btn {"pri" if pri else "gl"}">{btn}</div></div>'


CSS1 = open(D + '/sky1.css').read()
INTENT = " Light / Dark switch = design intent: follows device setting unless you choose (not built)."
CAPS = {
 'overview': ("Everything for today on one screen: example clips to swipe through, the one button to review them, and which platforms are planned." + INTENT,
              "Swipe the clip row left to peek at the next clip, tap Review one by one, then approve each. Approve all stays blocked until flags are resolved. Approve = draft only."),
 'queue': ("One example clip at a time. This one (clip 2) carries an open music flag, so its Approve button and Approve batch are blocked." + INTENT,
           "Swipe left or right to move to the next clip. Tap Edit to fix the flagged clip. Approve = send to Postiz as a draft only; nothing posts."),
 'earnings': ("Pooled earnings (no data yet) and one platform at a time. Whether a platform shares revenue data is Unverified. Bank check is a concept with dashes." + INTENT,
              "Tap a platform chip to see its detail. Nothing to approve here and nothing is connected."),
 'flags': ("Two example warnings with plain advice, both EXAMPLE only." + INTENT,
           "Tap Open clip to fix. While any flag is open, approving stays blocked."),
 'costs': ("An example monthly cost, the planned tools, and earnings with no data yet." + INTENT,
           "Just read. Nothing is billed or connected."),
 'connect': ("Four channel slots, all Not connected. YouTube is planned first. Icons are neutral shapes." + INTENT,
             "Tap Connect later; in this mockup the buttons do nothing and nothing posts."),
 'queue-empty': ("The Queue before any clip exists: No clips yet, with the next step." + INTENT,
                 "Tap Next: connect a channel (does nothing here)."),
 'flags-empty': ("The Flags tab when nothing needs fixing." + INTENT,
                 "Tap Back to Overview (does nothing here)."),
 'earnings-empty': ("The Earnings tab before any revenue data can be checked." + INTENT,
                    "Tap Next: connect a channel (does nothing here)."),
 'mac-overview': ("The Overview on a big screen, fitting one screen: today's approval, example warnings, and an example cost next to earnings (no data yet)." + INTENT,
                  "Review the example clips, glance at warnings, and check cost vs earnings. Approve = send to Postiz as a draft only; nothing posts."),
 'mac-more': ("Flags, Costs vs Earnings, Connect channels and Earnings together on one screen. Everything is example data or empty." + INTENT,
              "Scan only. Nothing is connected; buttons do nothing."),
}
def cap(k):
    a, b = CAPS[k]
    return f'<div class="cap"><p><b>What you\'re looking at:</b>{a}</p><p><b>What you do here:</b>{b}</p></div>'
def pstrip():
    return ('<div class="pstrip"><div class="plan">YouTube<small>Planned · first</small></div><div class="off">Instagram<small>Later</small></div>'
            '<div class="off">Facebook<small>Later</small></div><div class="off">TikTok<small>Later</small></div></div>')
def dots(on=0, hint=None):
    d = ''.join(f'<i class="{"on" if i==on else ""}"></i>' for i in range(3))
    return f'<div class="dotrow">{d}</div>' if not hint else f'<div class="dotrow"><span>‹</span>{d}<span>{hint}</span><span>›</span></div>'
def pin(): return f'<div class="glass pin"><div class="btn dis" style="width:100%">{I["ok"]}Approve batch</div>{BLK}{SAFE0}</div>'

def P_overview(theme):
    cards = ''.join(f'<div class="th th{i} cc">{I["play"]}<small>Example clip {i}</small></div>' for i in (1, 2, 3))
    return (f'<div class="in">{hdr(theme)}<h1 class="t">Hi Luis, your example clips are ready</h1>'
            f'<div class="rowh"><span class="k">Example clips</span><span class="swp">swipe ›</span></div><div class="cards">{cards}</div>{dots(0)}'
            f'<div class="hl">Approve your example clips<span>· Example: ~30 sec</span></div>'
            f'<div class="btn pri big">Review one by one</div><div class="btn dis">{I["ok"]}Approve all</div>{BLK}'
            f'{pstrip()}{SAFE0}</div>{nav(0)}')
def P_queue(theme):
    return (f'<div class="in">{hdr(theme)}<div class="rowh"><h1 class="t" style="margin:0">Approvals</h1><span class="chip">Example clip 2 of 3</span></div>'
            f'<div class="glass qcard"><div class="th th2">{I["play"]}<small>Example clip 2 of 3 · flagged</small></div><h3>Example clip 2</h3>'
            f'<div class="chips"><span class="chip plan">YouTube · planned</span><span class="chip warn dash">Flag · music (EXAMPLE)</span></div>'
            f'<div class="ft"><b>{MUSIC[0]}</b> {MUSIC[1]}</div>{qbtns(2)}</div>'
            f'{dots(1, "swipe")}{pin()}</div>{nav(1)}')
def P_earnings(theme):
    seg = ''.join(f'<div class="{"on" if i==0 else ""}">{n}</div>' for i, n in enumerate(['YouTube', 'TikTok', 'Instagram', 'Facebook']))
    return (f'<div class="in">{hdr(theme)}<h1 class="t">Earnings</h1>'
            f'<div class="glass card"><div class="k">Pooled earnings · No data yet</div>{HATCH(54)}<div class="sub" style="margin-top:6px;font-size:12px">Example shape only. No real revenue yet.</div></div>'
            f'<div class="seg">{seg}</div>'
            f'<div class="glass dcard"><div class="top"><b>YouTube</b><span class="chip dash">Revenue data: Unverified</span></div>'
            f'<div class="k" style="margin-bottom:6px">Bank cross-check (concept)</div>{bank()}</div></div>{nav(4)}')
def P_flags(theme):
    return (f'<div class="in">{hdr(theme)}<h1 class="t">Flags</h1><p class="sub" style="margin:0 2px">Example warnings to fix before approving</p>'
            f'{flag_card("m",2)}{flag_card("r",3)}{BLK}</div>{nav(2)}')
def P_costs(theme):
    return (f'<div class="in">{hdr(theme)}<h1 class="t">Costs vs Earnings</h1>'
            f'<div class="glass card">{cost_box()}<div class="k" style="margin-top:10px">Planned tools (not connected)</div>{plan_chips()}</div>'
            f'<div class="glass card">{earn_empty(70)}</div>{PWR}</div>{nav(3)}')
def P_connect(theme):
    return (f'<div class="in">{hdr(theme)}<h1 class="t">Connect channels</h1><p class="sub" style="margin:0 2px">Nothing is connected yet</p>'
            + ''.join(slot(n, g) for n, g in CH) + f'{SAFE0}</div>{nav(-1)}')
def P_empty(theme, ic, title, body, btn, pri, tab, h1):
    return (f'<div class="in">{hdr(theme)}<h1 class="t">{h1}</h1><div class="glass emp"><div class="ic">{I[ic]}</div><h3>{title}</h3><p>{body}</p><div class="btn {"pri" if pri else "gl"}">{btn}</div></div></div>{nav(tab)}')

def mac_overview1(theme):
    tabs = ''.join(f'<a class="{"on" if i==0 else ""}">{n}</a>' for i, n in enumerate(MTABS))
    vp = ('<div class="pl plan"><span>YouTube</span><small>Planned · first</small></div><div class="pl off"><span>Instagram</span><small>Later</small></div>'
          '<div class="pl off"><span>Facebook</span><small>Later</small></div><div class="pl off"><span>TikTok</span><small>Later</small></div>')
    return (f'<div class="in"><div class="mhdr">{reel()}<div class="tabsM">{tabs}</div>{toggle(theme, True)}</div>'
            f'<div class="g3"><div><h1 class="t">Hi Luis</h1><p class="sub" style="font-size:15px">Your example clips are ready.</p><div class="k" style="margin-top:26px">Platforms</div><div class="vp">{vp}</div></div>'
            f'<div class="glass card hero"><div class="fan">{thumbs()}</div><h2>Approve your example clips</h2><span class="dur" style="font-size:15px">Example: ~30 sec</span>'
            f'<div class="btns"><div class="btn dis">{I["ok"]}Approve all</div><div class="btn pri">Review one by one</div></div>{SAFE}</div>'
            f'<div class="stack"><div class="glass card"><div class="k">Policy flags · examples</div>{flag_rows()}</div><div class="glass card"><div class="k">Costs vs Earnings</div><div class="cv"><div class="bx">{cost_box()}</div><div class="bx">{earn_empty(36)}</div></div></div></div></div>{PWR}</div>')
def mac_more1(theme):
    tabs = ''.join(f'<a>{n}</a>' for n in MTABS)
    conn = ''.join(slot(n, g) for n, g in CH)
    return (f'<div class="in"><div class="mhdr">{reel()}<div class="tabsM">{tabs}</div>{toggle(theme, True)}</div>'
            f'<h1 class="t" style="margin:14px 4px 12px;font-size:30px">Flags, costs, earnings &amp; channels</h1>'
            f'<div class="m3"><div class="glass card"><div class="k">Policy flags · examples</div>{flag_rows()}</div>'
            f'<div class="glass card"><div class="k">Costs vs Earnings</div><div class="cv"><div class="bx">{cost_box()}</div><div class="bx">{earn_empty(40)}</div></div></div>'
            f'<div class="glass card"><div class="k">Connect channels</div>{conn}</div></div>'
            f'<div class="glass card" style="margin-top:16px"><div class="k">Earnings · by platform</div><div class="m2"><div>{earn_rows()}</div><div>{bank()}</div></div></div>{PWR}</div>')

manifest = []
def page(theme, name, body, mac, capkey, prefix='sky1'):
    w = 1476 if mac else 430
    frame = f'<div class="{"mac" if mac else "phone"}">{body}</div>'
    html = f'<!doctype html><meta charset="utf-8"><style>{TOK}{CSS}{CSS1}</style><body data-theme="{theme}" class="page" style="width:{w}px">{STAMP_M if mac else STAMP_P}{frame}{cap(capkey)}</body>'
    fn = f'{prefix}-{theme}-{name}'
    open(f'{D}/{fn}.html', 'w').write(html)
    manifest.append({'html': fn + '.html', 'png': f'clip-{fn}.png', 'w': w, 'dpr': 1.5 if mac else 2, 'name': name, 'theme': theme})
for th in ('light', 'dark'):
    page(th, 'phone-overview', P_overview(th), False, 'overview')
    page(th, 'phone-queue', P_queue(th), False, 'queue')
    page(th, 'phone-earnings', P_earnings(th), False, 'earnings')
    page(th, 'phone-flags', P_flags(th), False, 'flags')
    page(th, 'phone-costs', P_costs(th), False, 'costs')
    page(th, 'phone-connect', P_connect(th), False, 'connect')
    page(th, 'phone-queue-empty', P_empty(th, 'inbox', 'No clips yet', 'When your clip helper makes clips, they will show up here for your OK.', 'Next: connect a channel', True, 1, 'Approvals'), False, 'queue-empty')
    page(th, 'phone-flags-empty', P_empty(th, 'flag0', 'No flags', 'Nothing needs fixing right now. If a clip gets a copyright or monetization warning, it will show up here.', 'Back to Overview', False, 2, 'Flags'), False, 'flags-empty')
    page(th, 'phone-earnings-empty', P_empty(th, 'chart0', 'No earnings data yet', 'Earnings will show up here once a channel is connected and its revenue data can be checked.', 'Next: connect a channel', True, 4, 'Earnings'), False, 'earnings-empty')
    page(th, 'mac-overview', mac_overview1(th), True, 'mac-overview')
    page(th, 'mac-more', mac_more1(th), True, 'mac-more')

CHEV = '<svg viewBox="0 0 24 24"><path d="M6 9l6 6 6-6"/></svg>'
BACK = '<svg viewBox="0 0 24 24"><path d="M15 6l-6 6 6 6"/></svg>'
UNV = '<span class="chip dash">Revenue data: Unverified</span>'
LINE0 = '0 of 4 channels connected · Planned channels count as $0'
def prow(n, g, st, amt, cls=''):
    return f'<div class="prow {cls}"><div class="gl2">{I[g]}</div><div class="pn">{n}<div>{st}</div></div><div class="pa">{amt}</div></div>'
PLAN_YT = '<span class="chip plan">Planned · first</span>'
PLAN = '<span class="chip dash">Planned</span>'
def split_rows0():
    return (prow('YouTube', 'g_tri', PLAN_YT, '$0.00') + prow('TikTok', 'g_dia', PLAN, '$0.00') + prow('Instagram', 'g_ring', PLAN, '$0.00') + prow('Facebook', 'g_sq', PLAN, '$0.00')
            + f'<div class="prow tot"><div class="pn">Total</div><div class="pa">$0.00</div></div>')
def P_pooled(theme):
    cards = ''.join(f'<div class="th th{i} cc">{I["play"]}<small>Example clip {i}</small></div>' for i in (1, 2, 3))
    return (f'<div class="in">{hdr(theme)}<h1 class="t">Hi Luis, your example clips are ready</h1>'
            f'<div class="glass pool"><div class="ptop"><span class="k">Pooled revenue</span>{UNV}</div><div class="ptot">$0.00</div><div class="pline">{LINE0}</div>'
            f'<div class="phint">Tap for per-platform split {CHEV}</div></div>'
            f'<div class="rowh"><span class="k">Example clips</span><span class="swp">swipe ›</span></div><div class="cards sm">{cards}</div>{dots(0)}'
            f'<div class="hl">Approve your example clips<span>· Example: ~30 sec</span></div>'
            f'<div class="btn pri big">Review one by one</div><div class="btn dis">{I["ok"]}Approve all</div>{BLK}{SAFE0}</div>{nav(0)}')
def P_split(theme):
    return (f'<div class="in">{hdr(theme)}<div class="rowh"><span class="back">{BACK}Back to Overview</span></div><h1 class="t">Per-platform split</h1>'
            f'<div class="glass pool"><div class="ptop"><span class="k">Pooled revenue</span>{UNV}</div><div class="ptot">$0.00</div><div class="pline">{LINE0}</div>'
            f'<div style="margin-top:8px">{split_rows0()}</div></div></div>{nav(0)}')
def P_example(theme):
    rows = (prow('YouTube', 'g_tri', '<span class="chip ok dash">Connected (example)</span>', '<span class="exl">EXAMPLE</span>$123.45')
            + prow('TikTok', 'g_dia', PLAN, '$0.00') + prow('Instagram', 'g_ring', PLAN, '$0.00') + prow('Facebook', 'g_sq', PLAN, '$0.00')
            + '<div class="prow tot"><div class="pn">Total</div><div class="pa"><span class="exl">EXAMPLE</span>$123.45</div></div>')
    return (f'<div class="in">{hdr(theme)}<div class="rowh"><span class="back">{BACK}Back to Overview</span></div><h1 class="t">Per-platform split</h1>'
            f'<div class="glass pool"><div class="ribbon">EXAMPLE DATA, NOT REAL REVENUE</div><div class="ptop"><span class="k">Pooled revenue</span>{UNV}</div>'
            f'<div class="ptot"><span class="exl">EXAMPLE</span>$123.45</div><div class="pline">1 of 4 channels connected (example) · Planned channels count as $0</div>'
            f'<div style="margin-top:8px">{rows}</div></div></div>{nav(0)}')
def mac_pooled(theme):
    tabs = ''.join(f'<a class="{"on" if i==0 else ""}">{n}</a>' for i, n in enumerate(MTABS))
    pool = (f'<div class="glass pool" style="margin-top:22px"><div class="ptop"><span class="k">Pooled revenue</span></div><div style="margin-top:6px">{UNV}</div><div class="ptot">$0.00</div><div class="pline">{LINE0}</div>'
            f'<div class="phint">Click for per-platform split {CHEV}</div><div style="margin-top:6px">{split_rows0()}</div></div>')
    return (f'<div class="in"><div class="mhdr">{reel()}<div class="tabsM">{tabs}</div>{toggle(theme, True)}</div>'
            f'<div class="g3"><div><h1 class="t">Hi Luis</h1><p class="sub" style="font-size:15px">Your example clips are ready.</p>{pool}</div>'
            f'<div class="glass card hero"><div class="fan">{thumbs()}</div><h2>Approve your example clips</h2><span class="dur" style="font-size:15px">Example: ~30 sec</span>'
            f'<div class="btns"><div class="btn dis">{I["ok"]}Approve all</div><div class="btn pri">Review one by one</div></div>{SAFE}</div>'
            f'<div class="stack"><div class="glass card"><div class="k">Policy flags · examples</div>{flag_rows()}</div><div class="glass card"><div class="k">Costs vs Earnings</div><div class="cv"><div class="bx">{cost_box()}</div><div class="bx">{earn_empty(36)}</div></div></div></div></div>{PWR}</div>')
INTENT2 = " Light / Dark switch = design intent: follows device setting unless you choose (not built)."
CAPS.update({
 'pooled': ("Today on one screen, now with a pooled revenue card at the top: $0.00, because nothing is connected yet. Planned channels count as $0, and revenue data is Unverified." + INTENT2,
            "Tap the pooled revenue card to see the per-platform split. Swipe the clip row, then Review one by one. Approve = send to Postiz as a draft only; nothing posts."),
 'split': ("The split behind the pooled card: each platform's status and amount. Nothing is connected, so every channel is Planned and counts as $0.00." + INTENT2,
           "Tap Back to Overview to return. Nothing to approve here."),
 'example': ("A DEMO of how the card could look once one channel is connected. Every figure is stamped EXAMPLE and is not real revenue." + INTENT2,
             "Just look. Real figures only appear after a channel is connected AND the platform's revenue data is verified to be available; payouts also get cross-checked against bank deposits."),
 'mac-pooled': ("The Overview on a big screen with the pooled revenue card: $0.00 split into four Planned rows. Nothing is connected." + INTENT2,
                "Click the card to expand or collapse the split. Review the example clips; approving stays blocked until flags are resolved. Approve = draft only."),
})
for th in ('light', 'dark'):
    page(th, 'phone-overview-pooled', P_pooled(th), False, 'pooled', 'sky2')
    page(th, 'phone-pooled-split', P_split(th), False, 'split', 'sky2')
    page(th, 'phone-pooled-example', P_example(th), False, 'example', 'sky2')
    page(th, 'mac-overview-pooled', mac_pooled(th), True, 'mac-pooled', 'sky2')
json.dump(manifest, open(D + '/manifest.json', 'w'), indent=1)
