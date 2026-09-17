"""Create a new private report from measured data; refuse to overwrite an edition."""
import json
from pathlib import Path
import shutil

import markdown
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager

from run import STATE, HERE

NAMES={'incident':'로그 원인 분석','requirements':'개정 문서 조건 추출','call_chain':'호출 경로·단위 오류','change_impact':'수정 범위 판단'}
LABELS={'claude':'Claude · Opus 5','codex':'Codex · GPT-6 Astra'}


def delta(base, value):
    change=100*(value/base-1)
    return f'{abs(change):.1f}% '+('증가' if change>0 else '감소')


def draw_chart(data, directory, stem='comparison'):
    index={(r['provider'],r['arm']):r for r in data['aggregates']}
    font='/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'
    font_manager.fontManager.addfont(font)
    plt.rcParams.update({'font.family':font_manager.FontProperties(fname=font).get_name(),'font.size':12,'svg.fonttype':'none'})
    fig,axes=plt.subplots(2,1,figsize=(5.2,6.5),layout='constrained')
    xmax=max(index[p,'mixed'][k]/index[p,'frontier'][k] for p in LABELS for k in ('total_tokens','noncached_plus_output','seconds'))*1.26
    for ax,(provider,label) in zip(axes,LABELS.items()):
        f=index[provider,'frontier'];m=index[provider,'mixed']
        values=[m[k]/f[k] for k in ('total_tokens','noncached_plus_output','seconds')]
        ax.barh(['전체 클라우드 토큰','캐시 제외 입력+출력','전체 처리 시간'],values,color='#a34d2c',height=.45)
        ax.invert_yaxis();ax.axvline(1,color='#25272a',linestyle='--',linewidth=.8)
        ax.set_xlim(0,xmax);ax.set_title(label,loc='left',fontweight='bold',pad=12)
        ax.set_xlabel('직접 처리 = 1.00 · 낮을수록 적게 사용')
        for i,v in enumerate(values):ax.text(v+.035,i,f'{v:.2f}',va='center',bbox={'facecolor':'white','edgecolor':'none','pad':1})
        for spine in ax.spines.values():spine.set_visible(False)
        ax.tick_params(length=0);ax.grid(axis='x',alpha=.12);ax.set_axisbelow(True)
    for suffix in ('png','svg'):
        path=directory/(stem+'.'+suffix)
        if path.exists():raise RuntimeError('Preserve existing visual; choose a new edition name')
        fig.savefig(path,dpi=180,facecolor='white')
    plt.close(fig)


def make():
    data=json.loads((STATE/'analysis/results.json').read_text())
    if not data['complete'] or not data['protocol_valid']:raise RuntimeError('Complete valid measurements required')
    local=json.loads((STATE/'analysis/local-quality.json').read_text())
    review=json.loads((STATE/'analysis/content-review.json').read_text())
    directory=HERE.parent/'docs/local-delegation-20260917'
    directory.mkdir(parents=True,exist_ok=False)
    rows=data['rows']; index={(r['provider'],r['arm']):r for r in data['aggregates']}
    headline = ('이번 네 가지 작업에서는 두 클라이언트 모두 로컬 위임 후 전체 클라우드 토큰과 평균 처리 시간이 늘었습니다.'
                if all(index[p,'mixed']['total_tokens']>index[p,'frontier']['total_tokens'] and index[p,'mixed']['mean_seconds']>index[p,'frontier']['mean_seconds'] for p in LABELS)
                else '로컬 위임의 효과는 클라이언트와 작업에 따라 달랐습니다. 아래 표에서 직접 처리와 비교할 수 있습니다.')
    summary=['| 구성 | 엄격한 필드 일치 | 평균 시간 | 클라우드 전체 토큰 | 캐시 제외 입력+출력 |','|---|---:|---:|---:|---:|']
    changes=['| 메인 모델 | 전체 토큰 변화 | 캐시 제외 변화 | 평균 시간 변화 |','|---|---:|---:|---:|']
    details=[]
    for provider,label in LABELS.items():
        f=index[provider,'frontier'];m=index[provider,'mixed']
        changes.append(f"| {label} | {delta(f['total_tokens'],m['total_tokens'])} | {delta(f['noncached_plus_output'],m['noncached_plus_output'])} | {delta(f['mean_seconds'],m['mean_seconds'])} |")
        for arm,title in [('frontier','직접'),('mixed','로컬 위임·검토')]:
            a=index[provider,arm]
            summary.append(f"| {label} · {title} | {a['passed']}/{a['checks']} | {a['mean_seconds']:.1f}초 | {a['total_tokens']:,} | {a['noncached_plus_output']:,} |")
        detail=[f'**{label} 작업별 결과**','', '| 작업 | 토큰 변화 | 시간 직접 → 위임 | 필드 일치 직접 → 위임 |','|---|---:|---:|---:|']
        for task,title in NAMES.items():
            groups={arm:[r for r in rows if (r['provider'],r['task'],r['arm'])==(provider,task,arm)] for arm in ['frontier','mixed']}
            x,y=groups['frontier'],groups['mixed']
            tok=lambda a:sum(r['total_tokens'] for r in a)
            sec=lambda a:sum(r['seconds'] for r in a)/len(a)
            score=lambda a:f"{sum(r['passed'] for r in a)}/{sum(r['checks'] for r in a)}"
            detail.append(f'| {title} | {delta(tok(x),tok(y))} | {sec(x):.1f} → {sec(y):.1f}초 | {score(x)} → {score(y)} |')
        details.append('\n'.join(detail))
    draw_chart(data,directory)
    incident=[x for x in local if x['task']=='incident' and x['structured_answer_found']]
    local_scores=', '.join(sorted({f"{x['passed']}/{x['total']}" for x in incident}))
    repos=[r for r in rows if r['evidence_recall'] is not None]
    imperfect=[r for r in repos if not r['fully_correct']]
    authentic=sum(r['authentic_citations'] for r in rows);citations=sum(r['citations'] for r in rows)
    format_count=sum(len(r['format_only_differences']) for r in review['rows'])
    content_passed=sum(r['content_passed'] for r in review['rows']);content_total=sum(r['total'] for r in review['rows'])
    source_included=sum(r.get('included_source_spans',0) for r in review['rows']);source_required=sum(r.get('required_source_spans',0) for r in review['rows'])
    body=f'''# Claude·Codex 로컬 위임 실측

2026.09.17 · 같은 입력 4종 × 두 클라이언트 × 직접·위임 × 2회 = 32회

**{headline}**

Claude와 Codex가 같은 로컬 모델에 작업을 맡긴 뒤 최종 답을 검토하도록 비교했습니다. 정답률은 필드별 독립 검사로 계산했고, 시간에는 CLI 시작·로컬 처리·원문 검증·최종 응답을 모두 포함했습니다. 표의 토큰은 구성별 8회 합계이며 시간은 1회 평균입니다.

{chr(10).join(summary)}

표는 미리 고정한 정답과 필드 값을 그대로 비교한 점수입니다. 감점 중 {format_count}건은 `seconds` 뒤에 올바른 설명을 덧붙인 형식 차이였고, 이 차이를 구분한 내용 검토에서는 {content_passed}/{content_total}개 항목이 맞았습니다. 원래 점수는 바꾸지 않았으며 별도 검토 JSON에 사유를 남겼습니다.

각 서비스의 직접 처리 대비 변화입니다. 서로 다른 서비스의 절대 토큰 수보다 같은 서비스 안에서 위임 전후가 얼마나 달라졌는지 보는 것이 적절합니다.

{chr(10).join(changes)}

![직접 처리 대비 로컬 위임의 토큰과 시간 비율](comparison.svg)

{chr(10).join(details)}

최종 답의 정확도와 로컬 초안의 정확도는 다릅니다. 로그 분석에서 구조화된 로컬 답은 {local_scores}개 검사를 통과했습니다. 요청 ID 대신 시각을 쓰고, 실제 복구 설정과 다른 값을 제시하거나 근거 이벤트를 잘못 고른 사례가 있었습니다. 해당 실행의 메인 모델들은 원문을 읽고 최종 답을 수정했습니다. 로컬 답을 검토 없이 채택하는 방식의 정확도로 위 표를 읽으면 안 됩니다.

최종 인용 {citations}개 중 실제 원문과 일치한 것은 {authentic}개였습니다. 저장소 문제에서 요구한 근거 구간은 전체 답변 안에 {source_included}/{source_required}개 포함됐습니다. 기존 채점기는 특정 필드에 특정 줄을 연결해야 통과하므로, 올바른 추가 인용이나 다른 필드에 붙인 근거도 감점할 수 있습니다. 이 엄격한 근거 검사까지 모두 통과하지 못한 실행은 {len(imperfect)}/{len(repos)}회였지만 이를 곧바로 사실 오류율로 해석하지 않았습니다. 원래 근거 점수와 전체 답변의 근거 포함 여부를 모두 보존했습니다. 문서 문제에는 사실·출처 파일·이벤트 ID 검사를 적용했습니다.

실제 로컬 모델은 서버가 보고한 `Hermes3.6-35B-A3B-Uncensored-Genesis-V9-MTP-APEX.gguf`입니다. `arc-local`은 서버 별칭이고 `local-qwen`은 기존 도구 이름입니다. 이름만 보고 Qwen 가중치를 사용했다고 판단하지 않았습니다. Claude는 Opus 5, Codex는 GPT-6 Astra를 사용했고 두 메인의 추론 강도는 medium으로 맞췄습니다. 서로 다른 모델의 medium이 같은 계산량을 뜻하지는 않습니다.

기존 Claude 위임 코드의 `analyze_files`와 `explore_repository`를 두 클라이언트에서 그대로 호출했습니다. 로컬에 전달한 질문·입력 파일·출력 한도는 같았습니다. 메인 검증 도구는 양쪽 모두 같은 제한의 파일 읽기·검색·제출 도구로 맞췄습니다. 운영 세션의 전체 도구 구성과 시스템 지시문을 재현한 실험은 아닙니다. 실제 개인정보·운영 로그 대신 기존 비교 실험의 합성 입력을 재사용했습니다. 코드 구현 능력과 대규모 저장소는 이번 범위에 포함하지 않았습니다.

로컬 답변 파일 캐시는 껐지만 서버의 입력 처리 캐시는 비우지 않았습니다. 첫 로그 요청은 13.434초, 뒤의 같은 요청은 2.247초였고, 뒤 요청에서는 입력 24,729토큰 중 24,725토큰이 캐시로 보고됐습니다. 이 차이를 확인한 뒤 각 조건을 역순으로 한 번 더 실행했습니다. 최초 계획과 반복 추가 사유를 함께 보존했습니다. 이는 캐시 영향을 드러내기 위한 보완이며 완전히 통제된 콜드 캐시 실험은 아닙니다.

클라우드 전체 토큰은 캐시된 입력·새 입력·출력을 합산했습니다. Claude의 캐시 생성 입력과 CLI가 별도로 보고한 내부 모델 사용량도 포함했습니다. 캐시 제외 입력+출력은 캐시 읽기를 뺀 보조 지표입니다. 로컬 토큰은 클라우드 합계에 섞지 않았습니다. 두 서비스의 토크나이저와 내부 지시문이 다르고 구독 한도의 산정 방식도 이 수치만으로 알 수 없으므로, 구독 잔량 절약률이나 실제 요금으로 환산하지 않았습니다. 벤치마크 준비와 이 결과를 정리하는 대화의 토큰도 위 작업별 합계에는 포함하지 않았습니다.

표본은 네 가지 입력을 각각 두 번 실행한 결과입니다. 같은 문제를 반복했으므로 8개의 독립 문제를 평가한 것은 아닙니다. 캐시·서버 상태·응답 경로가 시간에 영향을 주므로 작은 차이를 일반화하면 안 됩니다. 이번 결과만으로 모든 탐색을 로컬에 먼저 맡기는 규칙을 권하기는 어렵습니다. 원문을 얼마나 읽어야 하는지와 메인의 검증 부담을 보고 위임 여부를 결정하는 편이 낫겠습니다. 더 큰 입력에서의 절약 효과는 이번 실험으로 확인하지 못했습니다. 전역 위임 규칙과 운영 서비스는 이 실험으로 바꾸지 않았습니다.

[실행별 수치](measurements.csv) · [집계·쌍별 비교](results.json) · [인용·정답 감사](audit.json) · [내용·형식 구분](content-review.json) · [로컬 초안 검사](local-quality.json)

토큰 수집은 CLI의 구조화된 완료 이벤트를 사용했습니다. Codex의 JSON 이벤트 출력은 [공식 비대화형 실행 문서](https://learn.chatgpt.com/docs/non-interactive-mode)를 참고했습니다.
'''
    (directory/'report.md').write_text(body)
    content=markdown.markdown(body,extensions=['tables'])
    content=content.replace('<table>','<div class="table-scroll"><table>').replace('</table>','</table></div>')
    css='''*{box-sizing:border-box}body{margin:0;color:#25272a;background:#fff;font-family:"Noto Sans CJK KR",sans-serif;line-height:1.8;word-break:keep-all}main{max-width:1020px;margin:auto;padding:60px 42px 90px}h1{font-family:"Noto Serif CJK KR",serif;font-size:38px;letter-spacing:-.03em}h1+p{font-size:13px;color:#62656a}p{margin:24px 0}table{border-collapse:collapse;width:100%;font-size:12px;font-variant-numeric:tabular-nums}th,td{padding:11px 8px;border-bottom:1px solid #ddd;white-space:nowrap;text-align:right}th:first-child,td:first-child{text-align:left}th{border-bottom-color:#25272a}.table-scroll{overflow-x:auto}img{display:block;width:100%;max-width:680px;margin:36px auto}a{color:#934121}code{font-size:.85em;overflow-wrap:anywhere}@media(max-width:600px){main{padding:28px 18px 60px}h1{font-size:27px}body{font-size:15px}th,td{padding:8px 6px}}@media print{@page{size:A4;margin:15mm}main{padding:0}body{font-size:9.5pt;line-height:1.6}h1{font-size:22pt}table{font-size:7pt}th,td{padding:5px}img{max-width:115mm;break-inside:avoid}.table-scroll{overflow:visible}p{margin:14px 0}a{color:inherit}}'''
    (directory/'report.html').write_text('<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Claude·Codex 로컬 위임 실측</title><style>'+css+'</style><main>'+content+'</main></html>')
    for name in ('results.json','measurements.csv','audit.json','local-quality.json','content-review.json'):shutil.copy2(STATE/'analysis'/name,directory/name)
    shutil.copytree(directory,STATE/'report')
    print(directory)


if __name__=='__main__':make()
