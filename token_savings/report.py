"""Create a new report edition from completed measurements. Never overwrite one."""
import argparse
import html
import json
from pathlib import Path
import statistics
import sys

from analyze import collect
from run import STATE, dump, benchmarks

NAMES={'claude':'Claude Opus 5','codex':'Codex GPT-6 Astra'}
ARMS={'direct':'직접 처리','tool':'도구로 위임','preflight':'사전 분석'}
TASKS={'incident':'장애 로그','requirements':'문서 요구사항','call_chain':'호출 경로','change_impact':'변경 영향'}


def comparison(data,provider,arm):
    return next(x for x in data['comparisons'] if x['provider']==provider and x['arm']==arm)


def local_review():
    out=[]
    for p in sorted((STATE/'runs').glob('*/capsule.json')):
        td=json.loads((p.parent/'task.json').read_text())
        if td['kind']!='documents':continue
        capsule=json.loads(p.read_text());g=p.parent/'local-grading'
        if not g.exists():
            g.mkdir();dump(g/'answer.json',capsule.get('draft',{}))
        quality=benchmarks.grade(g,td['task'],td['seed'])
        main=json.loads((p.parent/'summary.json').read_text())
        out.append(dict(run=p.parent.name,passed=quality['passed'],checks=quality['total'],
            wrong=[x for x in quality['checks'] if not x['passed']],main_passed=main['quality']['passed']))
    return out


def chart(data,directory):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    from PIL import Image
    font=font_manager.FontProperties(fname='/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')
    plt.rcParams['svg.fonttype']='none'
    fig,axes=plt.subplots(2,2,figsize=(10,5.3),layout='constrained')
    colors=['#b4b4b0','#62615f','#8b5b27']
    max_time=max(g['mean_seconds'] for g in data['groups'])*1.32
    max_tokens=max(g['total_tokens']/g['runs'] for g in data['groups'])*1.30
    for row,provider in enumerate(NAMES):
        gs=[next(g for g in data['groups'] if g['provider']==provider and g['arm']==a) for a in ARMS]
        for col,(key,divisor,title,limit) in enumerate([
            ('total_tokens',gs[0]['runs'],'평균 클라우드 토큰',max_tokens),
            ('mean_seconds',1,'평균 전체 시간(초)',max_time)]):
            ax=axes[row,col]
            vals=[g[key]/divisor for g in gs]
            ax.barh(range(3),vals,color=colors,height=.52)
            ax.set_yticks(range(3),[ARMS[g['arm']] for g in gs],fontproperties=font,fontsize=10)
            ax.invert_yaxis();ax.set_xlim(0,limit)
            ax.set_title(NAMES[provider]+' · '+title,fontproperties=font,fontsize=11,loc='left',pad=12)
            for i,v in enumerate(vals):
                ax.text(v+limit*.018,i,f'{v:,.0f}' if col==0 else f'{v:.1f}',va='center',fontsize=10,color='#292927')
            for spine in ax.spines.values():spine.set_visible(False)
            ax.tick_params(axis='both',length=0,labelsize=8)
            ax.xaxis.grid(True,color='#deded8',linewidth=.5);ax.set_axisbelow(True)
    fig.savefig(directory/'comparison.svg',bbox_inches='tight')
    fig.savefig(directory/'comparison.png',dpi=170,bbox_inches='tight')
    plt.close(fig)
    with Image.open(directory/'comparison.png') as im:
        im.resize((im.width//4,im.height//4)).save(directory/'comparison-25pct.png')


def table(headers,rows):
    esc=lambda v:html.escape(str(v))
    return '<div class="table-wrap"><table><thead><tr>'+''.join('<th>'+esc(h)+'</th>' for h in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+esc(x)+'</td>' for x in row)+'</tr>' for row in rows)+'</tbody></table></div>'


def build(directory):
    data=collect()
    if not data['complete']:raise RuntimeError('All 48 measurements must finish first')
    directory.mkdir(parents=True,exist_ok=False)
    local=local_review();dump(directory/'local-review.json',local);dump(directory/'results.json',data)
    summary=[];cache=[];tasks=[]
    for g in data['groups']:
        c=comparison(data,g['provider'],g['arm']) if g['arm']!='direct' else None
        summary.append([NAMES[g['provider']],ARMS[g['arm']],f"{g['total_tokens']:,}",
            f"{c['total_tokens_change_pct']:+.1f}%" if c else '기준',f"{g['passed']}/{g['checks']}",f"{g['mean_seconds']:.1f}초"])
        cache.append([NAMES[g['provider']],ARMS[g['arm']],f"{g['cached_input_tokens']:,}",
            f"{g['noncached_plus_output']:,}",f"{c['noncached_plus_output_change_pct']:+.1f}%" if c else '기준'])
    for provider in NAMES:
        for task in TASKS:
            subset=[r for r in data['rows'] if r['provider']==provider and r['task']==task]
            baseline=sum(r['total_tokens'] for r in subset if r['arm']=='direct')
            vals=[]
            for arm in ARMS:
                rows=[r for r in subset if r['arm']==arm]
                vals.append(f"{sum(r['total_tokens'] for r in rows):,}")
            saving=100*(sum(r['total_tokens'] for r in subset if r['arm']=='preflight')/baseline-1)
            tasks.append([NAMES[provider],TASKS[task],*vals,f'{saving:+.1f}%'])
    a=comparison(data,'claude','preflight');b=comparison(data,'codex','preflight')
    total=sum(r['checks'] for r in data['rows']);passed=sum(r['passed'] for r in data['rows'])
    seen=sum(r['evidence']['required_seen'] for r in data['rows']);required=sum(r['evidence']['required_spans'] for r in data['rows'])
    cited=sum(r['evidence']['required_cited'] for r in data['rows'])
    unseen=sum(len(r['evidence']['unseen_citations']) for r in data['rows'])
    raw_passed=sum(r['passed'] for r in local);raw_total=sum(r['checks'] for r in local)
    busy=[r['load'].get('processing_slots',0) for r in data['rows']]
    title='로컬 모델의 근거를 짧게 전달하면 토큰이 줄어드는가'
    lead=f"사전 분석의 총 클라우드 토큰은 직접 처리 대비 Claude {a['total_tokens_change_pct']:+.1f}%, Codex {b['total_tokens_change_pct']:+.1f}%였다. 최종 답의 사실·값 채점 결과는 전체 {passed}/{total}개다."
    recommendation='''이번 우선순위에서는 Codex의 사전 분석을 추천한다. 사실·값 80/80개를 유지하면서 총 토큰 48.7%, 캐시를 뺀 입력·출력 42.7%를 줄였다. Claude는 총량이 26.0% 줄었지만 캐시를 빼면 2.9% 늘어 절약 효과를 동일하게 평가하기 어렵다.'''
    method='''사용자가 정한 우선순위는 정확도, 클라우드 토큰 절약, 시간 순이다. 시간 증가만으로 후보를 제외하지 않는다. 채점 기준과 실행 조건은 중간에 바꾸지 않았다. 같은 과제 8건을 직접 처리, 도구로 위임, 사전 분석으로 나눠 두 클라이언트에서 총 48회 실행했다. 직접 처리도 필요한 원문만 검색해 읽었으며, 모든 조건에 서로 다른 줄 범위를 한 번에 읽는 도구와 같은 답 제출 형식을 제공했다. 사전 분석은 로컬 작업을 끝낸 후 첫 클라우드 입력에 결과를 붙인다. 도구 방식은 메인이 한 번 요청한 뒤 같은 형식의 결과를 받는다.'''
    mechanism='''로컬이 지정한 근거는 프로그램이 파일에서 다시 추출한다. 원문 해시와 경로 범위를 검사하고 짧은 파일은 전체 문맥을 포함한다. 메인에게는 상대 경로, 줄 번호, 근거와 답 초안만 전달하며 해시와 사용량은 별도 로그에 남긴다. 메인은 근거의 의미를 확인하고 초안의 오류를 고친다. 근거가 부족하면 추가 읽기를 허용했다.'''
    quality=f'''최종 사실 채점은 {passed}/{total}개다. 로컬 문서 초안만 채점하면 {raw_passed}/{raw_total}개이므로 로컬 답을 그대로 확정하는 방식은 검증하지 않았다. 필수 근거 줄의 메인 입력 포함 여부는 {seen}/{required}, 최종 인용 포함 여부는 {cited}/{required}다. 메인에게 보이지 않았던 비어 있지 않은 줄의 인용 내 등장 횟수는 {unseen}회이며 상세 목록은 results.json에 남겼다. 일부 답은 유효한 대체 근거를 인용했고 일부 코드 답은 해당 항목에 호출 관계의 근거를 직접 붙이지 않았다. 이 표의 정답률은 사실·값 채점이며 인용 표기가 모두 완벽하다는 뜻은 아니다. 원문 일치와 추론의 정당성은 구분했다.'''
    caveat=f'''장애 로그, 문서 개정, 호출 경로, 변경 영향이라는 네 종류의 합성 과제를 두 변형씩 사용했다. 코드 과제의 두 변형은 정답이 같고 방해 파일만 다르다. 실제 프로젝트 전체에 일반화할 수 없다. 로컬 모델은 arc-local 별칭의 Hermes3.6-35B-A3B-Uncensored-Genesis-V9-MTP-APEX다. 실험 중 공유 서버에는 각 실행 직전 {min(busy)}~{max(busy)}개 요청이 처리되고 있었다. 시간은 이 혼잡과 캐시의 영향을 받는다.'''
    accounting='''총 토큰은 클라이언트가 보고한 누적 입력과 출력의 합이며 캐시 입력도 포함한다. 캐시 입력을 뺀 양은 별도 표로 제시했다. 출력에 포함된 추론 토큰은 다시 더하지 않았다. 이는 구독 한도 절약률이나 실제 요금이 아니다. 전체 시간에는 로컬 분석, CLI 시작, 메인의 검증과 완료 응답이 포함된다. 이 대화에서 실험을 준비하고 보고서를 만든 사용량은 개별 과제 측정에서 제외했다.'''
    integration='''사전 분석은 메인 호출 전에 질문과 대상 문서 또는 저장소 범위를 정할 수 있을 때 적용한다. 정기 문서 검토나 범위가 정해진 코드 분석에 맞는다. 일반 채팅에서 메인이 이미 호출된 뒤 위임하면 도구 방식의 결과가 더 가깝다. 기존 대화 전체를 복사하거나 메인에게 같은 원문을 다시 모두 읽히면 이번 절약률을 기대할 수 없다. 전역 상시 위임 규칙을 켠 실험은 아니다. 측정한 것은 로컬 탐색, 근거 추출, 전달 형식과 호출 순서를 합친 효과이며 각 요소의 기여도를 따로 분리하지 않았다.'''
    limits='''메인 모델은 Claude Opus 5와 GPT-6 Astra, 사고 수준은 각각 medium이다. 공급자별 토크나이저와 숨겨진 기본 프롬프트가 다르므로 같은 클라이언트 안에서 조건을 비교한다. 응답 파일 캐시는 끄고 실행 순서를 회전·반전했지만 운영 서버의 KV 캐시와 클라우드 캐시는 비우지 않았다. 예비 실행은 본 표에서 제외했다. 과거 실험과 도구·근거 제출 방식이 달라 과거 숫자를 이번 대조군으로 재사용하지 않았다. Codex 직접 처리에서 빈 검색어 2회와 읽기 용량 초과 2회가 있었으며 재시도 비용도 모두 포함했다. 오류가 없었던 코드 과제 4쌍만 따로 비교해도 사전 분석은 총 토큰 45.4%, 캐시 제외 토큰 13.3%를 줄였다. 이 보조 비교는 과제 구성이 달라 본 결과를 대체하지 않는다.'''
    headings=['클라이언트','방식','총 토큰','직접 대비','정답','평균 전체 시간']
    chart(data,directory)
    styles='''*{box-sizing:border-box}body{margin:0;background:#fff;color:#242421;font-family:"Noto Sans CJK KR",sans-serif;font-size:14px;line-height:1.65;word-break:keep-all;font-variant-numeric:tabular-nums}main{max-width:1100px;margin:auto;padding:54px 46px}h1,h2{font-family:"Noto Serif CJK KR",serif;line-height:1.35;color:#191917}h1{font-size:35px;max-width:850px;margin:12px 0 25px}h2{font-size:24px;margin:28px 0 18px}p{margin:15px 0}.lead{font-size:18px}.meta{font-size:12px;color:#64645c}img{width:100%;height:auto;margin:12px 0}.table-wrap,.chart-wrap{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:12px;white-space:nowrap}th,td{padding:11px 10px;border-bottom:1px solid #d9d9d1;text-align:right}th:first-child,td:first-child,th:nth-child(2),td:nth-child(2){text-align:left}th{font-weight:500;color:#55554e}section{margin-bottom:40px}.note{font-size:12px;color:#55554e}@media(max-width:600px){main{padding:28px 20px}h1{font-size:27px}h2{font-size:21px}.lead{font-size:16px}table{font-size:11px}th,td{padding:9px 8px}.chart-wrap img{width:900px;max-width:none}}@page{size:A4;margin:17mm 15mm}@media print{body{font-size:10px;line-height:1.6}main{padding:0}h1{font-size:25px;margin:10px 0 18px}h2{font-size:18px;margin:16px 0 12px}.lead{font-size:12px}.meta,.note{font-size:9px}table{font-size:8px}th,td{padding:7px 5px}.table-wrap{overflow:visible}section{break-after:page;margin:0}section:last-child{break-after:auto}img{max-height:88mm;object-fit:contain}p{margin:12px 0}}'''
    sections=[f'<p class="meta">실험 기록 · 2026-09-17 · 48회 · 합성 자료</p><h1>{title}</h1><p class="lead">{lead}</p><p>{recommendation}</p>'+table(headings,summary)+'<div class="chart-wrap"><img src="comparison.svg" alt="조건별 클라우드 토큰과 전체 시간 비교"></div><p class="note">각 조건 8회 합계. 시간은 1회 평균이며 로컬 처리까지 포함한다. 표와 차트는 모바일에서 옆으로 밀어 볼 수 있다.</p>',
        '<h2>과제별 토큰과 정확도</h2>'+table(['클라이언트','과제','직접','도구','사전','사전 변화'],tasks)+f'<p>{quality}</p><h2>캐시를 뺀 사용량</h2>'+table(['클라이언트','방식','캐시 입력','비캐시 입력+출력','직접 대비'],cache),
        '<h2>검증을 유지하며 전달량과 왕복을 줄였다</h2>'+''.join('<p>'+s+'</p>' for s in [method,mechanism,integration,accounting,caveat,limits])+'<p class="note">원시 측정: measurements.csv · 자세한 채점: results.json · 로컬 초안: local-review.json. 기존 운영 설정에 이 실험 방식을 자동 적용하지 않았다.</p>']
    (directory/'report.html').write_text('<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+title+'</title><style>'+styles+'</style><main>'+''.join('<section>'+s+'</section>' for s in sections)+'</main></html>')
    md='# '+title+'\n\n'+lead+'\n\n'+recommendation+'\n\n'
    for hs,rows in [(headings,summary),(['클라이언트','과제','직접','도구','사전','사전 변화'],tasks)]:
        md+='| '+' | '.join(hs)+' |\n| '+' | '.join(['---']*len(hs))+' |\n'
        md+=''.join('| '+' | '.join(row)+' |\n' for row in rows)+'\n'
    md+='\n\n'.join([quality,method,mechanism,integration,accounting,caveat,limits])+'\n'
    (directory/'report.md').write_text(md)
    import shutil
    shutil.copy2(STATE/'analysis/measurements.csv',directory/'measurements.csv')
    shutil.copy2(STATE/'analysis/quality-review.json',directory/'quality-review.json')
    shutil.copy2(STATE/'analysis/sensitivity.json',directory/'sensitivity.json')
    if (STATE/'analysis/manual-review.json').exists():
        shutil.copy2(STATE/'analysis/manual-review.json',directory/'manual-review.json')
    print(json.dumps({'directory':str(directory),'quality':quality,'lead':lead},ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);a=p.parse_args();build(a.directory)
