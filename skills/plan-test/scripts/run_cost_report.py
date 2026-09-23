#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一次运行的成本报表（v0.10 AC-1）：主会话轮次/上下文/文档读取/子代理角色/评估行，从 ~/.claude/projects 的会话记录算出。
用法: python3 run_cost_report.py [--session-id ID] [--root ~/.claude/projects] [--json]
      python3 run_cost_report.py --list --since 2026-09-24T00:00:00Z   # 枚举候选主会话（是否调用 /plan-*、是否读过 phase 文档、是否编辑过 skill 目录）
口径与 ~/.plan-test 冻结基线（adhoc_stats.py r5）同源，逐项定义：
指标口径:
- 轮次 = 主 jsonl 中 type=assistant 且 message.usage 存在的记录数
- 每轮上下文 = cache_read_input_tokens + input_tokens + cache_creation_input_tokens，取中位/P90
- 带工具调用消息 = 按 message.id 归并后含 tool_use 的消息；单 Bash 独占 = 该消息只有一个 tool_use 且为 Bash
- skill 文档读取 = Read.file_path 或 Bash.command 含 'plan-test-skill/skills/' 或 '.claude/skills/plan-' 的调用，按 .md 文件计
- >8K 输出 = tool_result 文本长度 > 8000 的次数与字符和
- 子代理角色 = subagents/*.jsonl 首条 user 文本按关键词分类；输出 token = 该子代理 assistant usage.output_tokens 之和
- 压缩事件 = 含 "isCompactSummary":true 或 compact_boundary 的记录数
- prompts/ 读取 = skill 文档读取中路径含 plan-test/prompts/ 的次数（AC-3 用）
- 编辑过 prompts/ = Edit/Write/MultiEdit 的 file_path 含 /prompts/ 的次数（>0 的会话不计入发布后 5 次）
- 重复读取 = skill 文档读取总次数 − 去重文件数（AC-3b 用）
- Bash 段数 = 每条 Bash 命令按 &&、||、;、换行 切段（去掉 heredoc 正文）的段数，取中位（AC-4b 用）
- 评估行（r4）= 每个『评估』角色子代理：ROUND（首条 user 文本 `ROUND:\s*(\d)`，缺省 1）；verdict/硬伤数：对该子代理 assistant 文本块从后往前用 handoff_eval_result.extract_json 取第一个含 verdict 的 JSON；取不到 → 回读主会话 cwd 下 plans/ 与 cwd/.claude/worktrees/*/plans/ 内、mtime 落在该子代理时间窗（首条 ts − 60s，末条 ts + 3600s）内的 *handoff*eval*.json / handoff/eval-*.json（多份取 mtime 最近）；仍无 → verdict=unparsed、硬伤数=None、不计分母。硬伤数 = findings 里 fix_class=='硬伤' 的条数。AC-2b 分子 = 硬伤数之和，分母 = 非 unparsed 评估行数
- 非压缩重复读取（AC-3b 用）= 重复读取里，排除『压缩摘要记录之后 5 轮内对 RULES.md 或 phase-*.md 的读取』（那是规则要求的压缩后重读）
- 编辑过 skill 目录 = Edit/Write file_path 或 Bash 命令中出现 plan-test-skill/skills/ 或 .claude/skills/plan- 且该调用是写入（Edit/Write，或 Bash 含 cat >|tee|sed -i|> ）的次数（>0 的会话不计入发布后 5 次）
"""
import json,glob,os,re,sys,collections,argparse,datetime
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from handoff_eval_result import extract_json
def usage_rows(path):
    rows=[]
    with open(path,errors='ignore') as fh:
        for line in fh:
            try:o=json.loads(line)
            except: continue
            rows.append(o)
    return rows
def cls(t):
    t=t[:600]
    if re.search(r'交接|handoff|评估员|test-result-evaluator',t): return '评估'
    if re.search(r'challenger|挑战|closure|primary|specialist|synthesis',t,re.I): return '挑战'
    if re.search(r'审计|auditor|完成度',t): return '审计'
    if re.search(r'审查|review|reviewer|minimality',t,re.I): return 'review'
    if re.search(r'只读|调查|盘点|调研|Explore|搜|读',t): return '调研'
    return '其他'
def compute(session,root):
    root=os.path.expanduser(root)
    mains=glob.glob(f'{root}/*/{session}*.jsonl')
    if not mains: raise SystemExit('找不到会话记录：%s' % session)
    main_f=mains[0]; rows=usage_rows(main_f); a=type('A',(),{'session':session})
    turns=0; ctx=[]; msgs=collections.defaultdict(list); docs=collections.Counter(); big=0; bigch=0; comp=0; edp=0; segs=[]; edskill=0; aturn=0; lastcomp=-99; postcomp=0
    HD=re.compile(r"<<-?\s*['\"]?(\w+)['\"]?\n.*?\n\1\b",re.S)
    for o in rows:
        m=o.get('message',{})
        if o.get('isCompactSummary') or o.get('type')=='compact_boundary' or (isinstance(m,dict) and 'compact_boundary' in json.dumps(m)[:200]): comp+=1; lastcomp=aturn
        if o.get('type')=='assistant' and isinstance(m,dict):
            u=m.get('usage')
            if u: turns+=1; aturn+=1; ctx.append(u.get('cache_read_input_tokens',0)+u.get('input_tokens',0)+u.get('cache_creation_input_tokens',0))
            for p in m.get('content') or []:
                if isinstance(p,dict) and p.get('type')=='tool_use':
                    msgs[m.get('id') or o.get('uuid')].append(p['name'])
                    if p['name']=='Bash': segs.append(len([x for x in re.split(r'&&|\|\||;|\n',HD.sub('',p['input'].get('command',''))) if x.strip()]))
                    inp=p.get('input',{}); s=str(inp.get('file_path','') or inp.get('command',''))
                    if p['name'] in('Edit','Write','MultiEdit') and '/prompts/' in str(inp.get('file_path','')): edp+=1
                    if ('plan-test-skill/skills/' in s or '.claude/skills/plan-' in s) and (p['name'] in('Edit','Write','MultiEdit') or (p['name']=='Bash' and re.search(r'cat\s*>|tee\s|sed\s+-i|\s>\s',s))): edskill+=1
                    for mm in re.findall(r'(?:plan-test-skill/skills/|\.claude/skills/)([\w./-]+\.md)',s):
                        if docs[mm]>=1 and aturn-lastcomp<=5 and (mm.endswith('RULES.md') or re.search(r'phase-[A-Za-z0-9-]+\.md$',mm)): postcomp+=1
                    for mm in re.findall(r'(?:plan-test-skill/skills/|\.claude/skills/)([\w./-]+\.md)',s): docs[mm]+=1
        if o.get('type')=='user' and isinstance(m,dict):
            for p in m.get('content') or []:
                if isinstance(p,dict) and p.get('type')=='tool_result':
                    c=p.get('content'); s=c if isinstance(c,str) else ' '.join(x.get('text','') for x in c if isinstance(x,dict)) if isinstance(c,list) else ''
                    if len(s)>8000: big+=1; bigch+=len(s)
    ctx.sort(); nm=len(msgs); sb=sum(1 for v in msgs.values() if v==['Bash'])
    subs=collections.defaultdict(lambda:[0,0]); evals=[]
    cwd=next((o.get('cwd') for o in rows if o.get('cwd')),None)
    def ts2e(x): return datetime.datetime.fromisoformat(x.replace('Z','+00:00')).timestamp()
    for sf in glob.glob(main_f[:-6]+'/subagents/*.jsonl'):
        first=''; out=0; texts=[]; tss=[]
        for o in usage_rows(sf):
            m=o.get('message',{})
            if o.get('timestamp'): tss.append(o['timestamp'])
            if not first and o.get('type')=='user':
                c=m.get('content'); first=' '.join(p.get('text','') for p in c if isinstance(p,dict)) if isinstance(c,list) else str(c)
            if o.get('type')=='assistant' and isinstance(m,dict):
                if m.get('usage'): out+=m['usage'].get('output_tokens',0)
                for p in m.get('content') or []:
                    if isinstance(p,dict) and p.get('type')=='text': texts.append(p['text'])
        r=cls(first); subs[r][0]+=1; subs[r][1]+=out
        if r!='评估': continue
        rd=re.search(r'ROUND:\s*(\d)',first); rd=int(rd.group(1)) if rd else 1
        j=None; src='text'
        for t in reversed(texts):
            try: cand=extract_json(t)
            except Exception: cand=None
            if isinstance(cand,dict) and 'verdict' in cand: j=cand; break
        if j is None and cwd and tss:
            lo,hi=ts2e(min(tss))-60,ts2e(max(tss))+3600
            pats=[os.path.join(cwd,'plans','**','*handoff*eval*.json'),os.path.join(cwd,'plans','**','handoff','eval-*.json'),os.path.join(cwd,'.claude','worktrees','*','plans','**','*handoff*eval*.json'),os.path.join(cwd,'.claude','worktrees','*','plans','**','handoff','eval-*.json')]
            cands=[(os.path.getmtime(p),p) for pat in pats for p in glob.glob(pat,recursive=True) if lo<=os.path.getmtime(p)<=hi]
            for _,p in sorted(cands,reverse=True):
                try: cand=json.load(open(p))
                except Exception: continue
                if isinstance(cand,dict) and 'verdict' in cand: j=cand; src='file'; break
        if j is None: evals.append((os.path.basename(sf)[6:14],rd,'unparsed',None,'-'))
        else: evals.append((os.path.basename(sf)[6:14],rd,j.get('verdict','?'),sum(1 for x in j.get('findings') or [] if isinstance(x,dict) and x.get('fix_class')=='硬伤'),src))
    R={'session':a.session[:8]}
    R['轮次']=turns
    R['每轮上下文中位']=ctx[len(ctx)//2] if ctx else 0; R['每轮上下文P90']=ctx[int(len(ctx)*.9)] if ctx else 0
    R['带工具调用消息']=nm; R['单Bash独占']=sb; R['单Bash独占比例%']=sb*100//max(nm,1)
    R['skill文档读取']=sum(docs.values()); R['skill文档读取按文件']=dict(docs.most_common())
    R['大输出次数']=big; R['大输出字符']=bigch
    R['压缩事件']=comp; R['prompts读取']=sum(v for k,v in docs.items() if 'prompts/' in k); R['编辑过prompts']=edp
    R['子代理']={k:{'个数':v[0],'输出token':v[1]} for k,v in sorted(subs.items())}
    R['重复读取']=sum(docs.values())-len(docs)
    segs.sort(); R['Bash段数中位']=segs[len(segs)//2] if segs else 0
    valid=[e for e in evals if e[2]!='unparsed']; R['评估行']=[{'子代理':e[0],'ROUND':e[1],'verdict':e[2],'硬伤数':e[3],'来源':e[4]} for e in evals]; R['有效评估行']=len(valid); R['硬伤合计']=sum(e[3] for e in valid); R['unparsed']=len(evals)-len(valid)
    R['非压缩重复读取']=sum(docs.values())-len(docs)-postcomp; R['压缩后规则重读']=postcomp; R['编辑过skill目录']=edskill
    R['读过phase文档']=any(re.search(r'phase-[A-Za-z0-9-]+\.md$',k) for k in docs)
    return R

def render(R):
    L=[f"# 成本报表 {R['session']}",
       f"- 轮次: {R['轮次']}；每轮上下文: 中位 {R['每轮上下文中位']}, P90 {R['每轮上下文P90']}；压缩事件: {R['压缩事件']}",
       f"- 带工具调用消息: {R['带工具调用消息']}, 单 Bash 独占: {R['单Bash独占']} ({R['单Bash独占比例%']}%)；Bash 段数中位: {R['Bash段数中位']}",
       f"- skill 文档读取: {R['skill文档读取']} 次（重复 {R['重复读取']}，非压缩重复 {R['非压缩重复读取']}，prompts/ {R['prompts读取']}）; " + ', '.join(f'{k} {v}' for k,v in list(R['skill文档读取按文件'].items())[:6]),
       f"- >8K 输出: {R['大输出次数']} 次, {R['大输出字符']} 字符；编辑过 skill 目录: {R['编辑过skill目录']}",
       "- 子代理: " + ', '.join(f"{k} {v['个数']} 个/{v['输出token']} out" for k,v in R['子代理'].items()),
       "- 评估行: " + '; '.join(f"{e['子代理']} R{e['ROUND']} {e['verdict']} 硬伤{e['硬伤数']} ({e['来源']})" for e in R['评估行']) + f" | 有效 {R['有效评估行']} 行, 硬伤合计 {R['硬伤合计']}, unparsed {R['unparsed']}"]
    return '\n'.join(L)

def list_sessions(root,since):
    root=os.path.expanduser(root); out=[]
    for f in sorted(glob.glob(root+'/*/*.jsonl')):
        try:
            with open(f,errors='ignore') as fh: txt=fh.read()
        except Exception: continue
        m=re.search(r'"timestamp":\s*"([^"]+)"',txt)
        if not m or (since and m.group(1)<since): continue
        if not re.search(r'\\?"skill\\?":\\?"plan-(test|task|bs)\\?"|/plan-(test|task|bs)\b',txt): continue
        sid=os.path.basename(f)[:-6]
        try: R=compute(sid,root)
        except SystemExit: continue
        out.append({'session':sid,'start':m.group(1),'读过phase文档':R['读过phase文档'],'编辑过skill目录':R['编辑过skill目录'],'轮次':R['轮次']})
    return out

def main(argv=None):
    ap=argparse.ArgumentParser(description='一次运行的成本报表')
    ap.add_argument('--session-id',default=os.environ.get('CLAUDE_CODE_SESSION_ID'))
    ap.add_argument('--root',default='~/.claude/projects'); ap.add_argument('--json',action='store_true')
    ap.add_argument('--list',action='store_true'); ap.add_argument('--since')
    a=ap.parse_args(argv)
    if a.list:
        rows=list_sessions(a.root,a.since)
        print(json.dumps(rows,ensure_ascii=False,indent=1) if a.json else '\n'.join(f"{r['session'][:8]} {r['start'][:16]} phase文档={'是' if r['读过phase文档'] else '否'} 编辑skill={r['编辑过skill目录']} 轮次={r['轮次']}" for r in rows))
        return 0
    if not a.session_id: raise SystemExit('缺少 --session-id，且环境变量 CLAUDE_CODE_SESSION_ID 为空')
    R=compute(a.session_id,a.root)
    print(json.dumps(R,ensure_ascii=False,indent=1) if a.json else render(R))
    return 0

if __name__=='__main__': sys.exit(main())
