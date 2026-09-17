"""Export an immutable report from measured main, worker, and local calls."""
import argparse
import json
from pathlib import Path
import statistics

import markdown
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager

from analyze import export, aggregate

NAMES={'incident':'로그 원인 분석','requirements':'개정 문서 추출','cache_fix':'캐시 버그 수정','scheduler':'스케줄러 구현'}
LABELS={'claude':'Claude · Opus 5','codex':'Codex · Astra'}
INK='#25272a';ACCENT='#a54b2a';GRAY='#6c6e72'


def pct(base,mixed):return 100*(1-mixed/base) if base else 0

def change(base,mixed):
    saving=pct(base,mixed)
    return f'{abs(saving):.1f}% '+('감소' if saving>=0 else '증가')


def sums(rows):
    return {key:sum(r[key] for r in rows) for key in ['total_cloud_tokens','frontier_tokens','fresh_input','cached_input','cache_write_input','output','reference_usd','wall_seconds','local_tokens','local_seconds','worker_calls','local_calls','passed_checks','total_checks']}


def mobile_chart(data,directory):
    index={(x['provider'],x['arm']):x for x in data['aggregate']}
    font='/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'
    font_manager.fontManager.addfont(font)
    plt.rcParams.update({'font.family':font_manager.FontProperties(fname=font).get_name(),'font.size':11,'svg.fonttype':'none'})
    fig,axes=plt.subplots(2,1,figsize=(4.5,6.5),layout='constrained')
    for ax,(provider,label) in zip(axes,LABELS.items()):
        f=index[provider,'frontier'];m=index[provider,'mixed']
        values=[m[k]/f[k] for k in ['total_cloud_tokens','reference_usd','wall_seconds']]
        ax.barh(['클라우드 토큰','API 환산 비용','소요 시간'],values,color=ACCENT,height=.46)
        ax.invert_yaxis();ax.axvline(1,color=INK,linestyle='--',linewidth=1)
        ax.set_title(label,loc='left',fontweight='bold',pad=16)
        ax.set_xlim(0,max(values)*1.24);ax.set_xlabel('메인 단독 = 1.00')
        for i,v in enumerate(values):ax.text(v+max(values)*.025,i,f'{v:.2f}',va='center',fontsize=10)
        for spine in ax.spines.values():spine.set_visible(False)
        ax.tick_params(axis='both',length=0);ax.grid(axis='x',alpha=.12);ax.set_axisbelow(True)
    fig.savefig(directory/'comparison-mobile.svg',facecolor='white');plt.close(fig)


def mobile_document(document):
    old='<img alt="메인 단독 대비 자동 분담의 토큰·API 환산 비용·소요 시간 비율" src="comparison.svg" />'
    new='<picture><source media="(max-width:600px)" srcset="comparison-mobile.svg">'+old+'</picture>'
    document=document.replace(old,new)
    document=document.replace('img{min-width:660px;margin-top:24px}','img{margin-top:24px}')
    document=document.replace('</style>','.mobile-hint{display:none}@media(max-width:600px){.mobile-hint{display:block;font-size:12px;color:#6c6e72}} </style>')
    return document.replace('<div class="table-scroll">','<p class="mobile-hint">표는 좌우로 움직여 볼 수 있습니다.</p><div class="table-scroll">',1)


def make(directory):
    data=export(directory);rows=data['rows']
    index={(x['provider'],x['arm']):x for x in data['aggregate']}
    for provider in LABELS:
        for arm in ['frontier','mixed','delegated']:
            if (provider,arm) not in index:
                raise RuntimeError(f'Missing completed comparison: {provider}/{arm}')
    primary=['| 메인 모델 | 클라우드 토큰 | API 환산 비용 | 소요 시간 | 정답 검사 |',
             '|---|---:|---:|---:|---:|']
    absolute=['| 구성 | 실행 수 | 클라우드 토큰 | API 환산 USD | 총 소요 시간 | 로컬 / 하위 호출 |',
              '|---|---:|---:|---:|---:|---:|']
    for provider,label in LABELS.items():
        f=index[provider,'frontier'];m=index[provider,'mixed']
        primary.append(f"| {label} | {change(f['total_cloud_tokens'],m['total_cloud_tokens'])} | {change(f['reference_usd'],m['reference_usd'])} | {m['wall_seconds']/f['wall_seconds']:.2f}배 | {f['passed_checks']}/{f['total_checks']} → {m['passed_checks']}/{m['total_checks']} |")
        for arm,title in [('frontier','메인 단독'),('mixed','자동 분담')]:
            a=index[provider,arm]
            absolute.append(f"| {label} · {title} | {a['runs']} | {a['total_cloud_tokens']:,} | ${a['reference_usd']:.4f} | {a['wall_seconds']:.1f}초 | {a['local_calls']} / {a['worker_calls']} |")
    detail=['| 메인 모델 / 작업 | 토큰 변화 | API 환산 변화 | 시간 배율 | 정답 검사 단독 → 분담 |',
            '|---|---:|---:|---:|---:|']
    for provider,label in LABELS.items():
        for task,title in NAMES.items():
            f=sums([r for r in rows if (r['provider'],r['task'],r['arm'])==(provider,task,'frontier')])
            m=sums([r for r in rows if (r['provider'],r['task'],r['arm'])==(provider,task,'mixed')])
            detail.append(f"| {label} / {title} | {change(f['total_cloud_tokens'],m['total_cloud_tokens'])} | {change(f['reference_usd'],m['reference_usd'])} | {m['wall_seconds']/f['wall_seconds']:.2f}배 | {f['passed_checks']}/{f['total_checks']} → {m['passed_checks']}/{m['total_checks']} |")
    delegated=['| 메인 → 구현 담당 | 토큰 변화 | API 환산 변화 | 시간 배율 | 정답 검사 단독 → 위임 |',
               '|---|---:|---:|---:|---:|']
    forced_counts=[]
    for provider,label in LABELS.items():
        dr=[r for r in rows if r['provider']==provider and r['arm']=='delegated']
        keys={(r['task'],r['seed']) for r in dr}
        fr=[r for r in rows if r['provider']==provider and r['arm']=='frontier' and (r['task'],r['seed']) in keys]
        f=sums(fr);m=sums(dr)
        worker='Sonnet' if provider=='claude' else 'Terra'
        delegated.append(f"| {label} → {worker} | {change(f['total_cloud_tokens'],m['total_cloud_tokens'])} | {change(f['reference_usd'],m['reference_usd'])} | {m['wall_seconds']/f['wall_seconds']:.2f}배 | {f['passed_checks']}/{f['total_checks']} → {m['passed_checks']}/{m['total_checks']} |")
        forced_counts.append(f"{label} {len(dr)}건에서 하위 호출 {m['worker_calls']}회")
    font='/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'
    font_manager.fontManager.addfont(font)
    plt.rcParams.update({'font.family':font_manager.FontProperties(fname=font).get_name(),'font.size':11,'text.color':INK,'axes.labelcolor':INK,'xtick.color':GRAY,'ytick.color':INK,'svg.fonttype':'none'})
    fig,axes=plt.subplots(1,2,figsize=(10.5,3.4),layout='constrained')
    for ax,(provider,label) in zip(axes,LABELS.items()):
        f=index[provider,'frontier'];m=index[provider,'mixed']
        values=[m[k]/f[k] for k in ['total_cloud_tokens','reference_usd','wall_seconds']]
        ax.barh(['클라우드 토큰','API 환산 비용','소요 시간'],values,color=ACCENT,height=.46)
        ax.invert_yaxis();ax.axvline(1,color=INK,linestyle='--',linewidth=1)
        ax.set_title(label,loc='left',fontweight='bold',pad=20)
        ax.set_xlim(0,max(values)*1.22);ax.set_xlabel('메인 단독 = 1.00')
        for i,v in enumerate(values):ax.text(v+max(values)*.025,i,f'{v:.2f}',va='center',fontsize=11)
        for spine in ax.spines.values():spine.set_visible(False)
        ax.tick_params(axis='both',length=0);ax.grid(axis='x',alpha=.12);ax.set_axisbelow(True)
    fig.savefig(directory/'comparison.svg',facecolor='white')
    fig.savefig(directory/'comparison.png',dpi=180,facecolor='white');plt.close(fig)
    mobile_chart(data,directory)
    quality_same=all(p['quality_delta']==0 for p in data['pairs'])
    quality_sentence='이번 검사에서 정답률 차이는 없었습니다.' if quality_same else '일부 작업에서 정답률 차이가 나타났습니다. 아래 작업별 결과를 확인해야 합니다.'
    successful=sum(r['fully_correct'] for r in rows)
    local_tokens=sum(r['local_tokens'] for r in rows)
    worker_calls=sum(r['worker_calls'] for r in rows)
    failures=sum(sum(r['failed_tools'].values()) for r in rows)
    body=f'''# 모델 역할 분담 실험 결과

2026.09.14 · 구독 CLI + 로컬 Qwen · 실전 설정 적용 전 비교

**Claude의 메인은 요청대로 Opus 5로 바꿨습니다.** Codex는 GPT-6 Astra를 사용했습니다. 두 서비스 모두 메인 단독 구성과 자동 분담 구성을 같은 문제로 비교했고, 코드 작업을 하위 모델에 반드시 한 번 맡기는 추가 실험도 진행했습니다.

{quality_sentence} 다만 같은 정답률이라도 토큰과 시간이 함께 줄어드는 것은 아닙니다. 다음 표는 각 서비스의 메인 단독 대비 자동 분담 변화입니다.

{chr(10).join(primary)}

![메인 단독 대비 자동 분담의 토큰·API 환산 비용·소요 시간 비율](comparison.svg)

**API 환산 비용은 비교용 지표입니다. 구독 한도 절감률이나 실제 결제액이 아닙니다.** 클라우드 토큰에는 캐시로 재사용한 입력도 포함했습니다. 로컬 토큰은 별도 집계했습니다. 정확한 구독 한도 차감 비율은 이 기록으로 계산할 수 없습니다.

자동 분담의 역할은 아래와 같습니다. 메인은 작업을 나누고 중요한 근거를 확인하며 최종 결과를 승인합니다. 긴 자료는 Qwen에 먼저 읽히고, 구현 규모가 충분하면 하위 모델에 맡깁니다. 작은 작업은 메인이 직접 수행할 수 있습니다.

| 역할 | Claude 구성 | Codex 구성 |
|---|---|---|
| 판단·최종 검토 | Opus 5 · medium | GPT-6 Astra · medium |
| 구현 담당 | Sonnet | GPT-5.6 Terra |
| 탐색 담당 | Haiku | GPT-5.6 Luna |
| 긴 로그·문서 분석 | 로컬 Qwen / arc-local | 로컬 Qwen / arc-local |

{chr(10).join(absolute)}

작업별 결과를 보면 어디에 분담이 도움이 되는지 확인할 수 있습니다. 로그는 잘못 적용된 재시도 단위를 찾아야 하고, 문서는 개정 순서를 따르면서 기한·예산·제출 조건을 추출해야 합니다. 코드 작업은 TTL 캐시의 경계 조건과 작업 스케줄러의 중복·순서·그룹 처리 규칙을 검사합니다.

{chr(10).join(detail)}

작은 코드 작업에서 자동 분담이 구현 담당을 호출하지 않는 경우가 나왔습니다. 그래서 기존 결과를 보존하고, 같은 코드 문제를 구현 담당에 한 번 넘긴 뒤 메인이 검토하도록 별도 비교했습니다. 아래 수치는 같은 작업·같은 반복 번호의 메인 단독 결과를 기준으로 계산했습니다. 자동 분담 표와 합치지 않았습니다.

{chr(10).join(delegated)}

명시적 위임 실행 수는 {', '.join(forced_counts)}입니다. 이 추가 실험은 자동 분담 결과를 본 뒤 설계했으므로 탐색적 결과로 봐야 합니다. 하위 모델의 구현 비용과 메인의 검토 비용을 모두 합산했습니다.

전체 {len(rows)}회 중 모든 정답 검사를 통과한 실행은 {successful}회입니다. 구현 담당 호출은 총 {worker_calls}회, 로컬 처리량은 {local_tokens:,}토큰입니다. 오류로 기록된 도구 호출은 {failures}회입니다. 백업 확장자 또는 파일명에 포함된 따옴표 때문에 거부된 쓰기 시도였고, 모델은 이후 작업을 완료했습니다. 도구 자체의 원본 백업은 별도로 보존했습니다. Haiku·Luna는 별도 읽기 전용 점검에서 코드의 계약 위반 세 가지를 찾아 정상 호출을 확인했습니다. 독립 탐색 작업의 절약률과 품질은 이번 비교 범위에 포함하지 않았습니다. Claude CLI가 내부적으로 호출한 Haiku 보조 모델은 별도 위임과 구분했고 클라우드 총량에는 포함했습니다. 따라서 메인 단독이라는 표현은 사용자가 설정한 작업 모델 기준입니다.

최종 코드를 읽는 과정에서 기존 검사가 빠뜨린 경계 조건을 발견했습니다. 캐시 계약은 실제 저장 항목을 삭제하면 참을 반환하도록 요구하지만, Claude 결과물은 만료된 항목을 제거하고도 거짓을 반환했습니다. 단독·자동 분담·명시적 위임에서 공통으로 나타났습니다. 이 조건을 모든 캐시 결과물에 똑같이 추가 검사했으며 원래 점수와 파일을 보존했습니다. 표는 추가 검사를 반영한 점수입니다. Codex 결과물은 이 검사도 통과했습니다. 따라서 여기서 정답률 차이가 없다는 말은 각 서비스 안에서 분담 전후의 차이가 없다는 뜻입니다.

실험은 서비스별로 네 가지 합성 작업을 두 번씩 수행했습니다. 코드 두 문제는 같은 문제의 반복 실행이고, 로그·문서는 반복 번호에 따라 일부 값과 잡음이 달라집니다. 정답과 비공개 검사는 모델 작업 폴더 밖에 두었습니다. 메인 모델, 추론 노력 medium, 기본 파일·테스트 도구를 맞췄고, 단독과 자동 분담의 실행 순서를 번갈아 배치했습니다. 클라우드 구현 담당도 medium으로 실행했습니다.

Codex 로그 분석에서는 원문 읽기가 줄어도 근거 확인을 여러 번 나눠 호출하면서 대화 입력이 반복됐습니다. 다음 개선 후보는 여러 근거 구간을 한 번에 반환하는 도구와 더 짧은 작업 지시문입니다. 이번 실험 중 자동 분담 규칙은 고치지 않았으며, 이 개선안의 절약 효과는 아직 측정하지 않았습니다. 초기 연결 점검과 탐색 모델의 호출 점검은 작업별 비교 합계에서 제외했습니다.

표의 시간은 모델 실행부터 최종 응답까지이며 시작 비용, 도구 실행, 위임, 로컬 대기가 포함됩니다. 두 서비스 실험은 일부 병행했고 Qwen은 한 번에 한 요청만 처리하게 했으므로 로컬 대기열이 영향을 줄 수 있습니다. 메인 단독 대비 관측 시간을 보여 주지만 하드웨어의 고유 속도 차이로 해석할 수는 없습니다. 캐시를 강제로 비우지 않았으므로 이전 실행의 캐시 효과도 남습니다.

**현재 판단은 전면 적용 보류입니다.** 절약이 관측된 작업부터 제한적으로 재검증하는 편이 좋습니다. 긴 자료를 자주 처리하는지, 응답 시간이 얼마나 중요한지에 따라 실익이 달라집니다. 작은 코드 작업의 위임 비용과 검토 비용을 무시하고 모든 일을 하위 모델에 넘길 근거는 부족합니다. 이번 표본으로 대규모 저장소 수정, 설계 판단, 실제 장애 대응의 품질까지 보장할 수 없습니다.

실험 구성은 별도 프로젝트에 두었습니다. 전역 Claude·Codex 설정에는 적용하지 않았고 추가 크레딧을 켜지 않았습니다. 인증·세션·실행 기록·결과물은 vault 안에 저장했습니다. 원시 결과를 보려면 같은 폴더의 [실행별 CSV](runs.csv)와 [집계 JSON](results.json)을 확인할 수 있습니다.

사용량은 각 CLI의 구조화된 응답에서 수집했습니다. Claude는 CLI가 보고한 모델별 사용량과 기준 비용을 사용했고, Codex는 입력·캐시·출력 토큰에 공식 API 단가를 적용했습니다. 추론 토큰을 출력 토큰에 다시 더하지 않았습니다. [Claude 모델 설정](https://code.claude.com/docs/en/model-config), [Claude CLI](https://code.claude.com/docs/en/cli-reference), [Astra 단가](https://developers.openai.com/api/docs/models/gpt-6-astra), [Terra 단가](https://developers.openai.com/api/docs/models/gpt-5.6-terra), [Luna 단가](https://developers.openai.com/api/docs/models/gpt-5.6-luna)를 기준으로 구성했습니다.
'''
    (directory/'report.md').write_text(body)
    audit={'draft_rules_applied':True,'external_text_service_used':False,'postdraft_change_ratio':0,
           'note':'Korean drafted directly under local style rules; numbers generated from measured data.'}
    (directory/'writing-check.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2))
    content=markdown.markdown(body,extensions=['tables','fenced_code'])
    content=content.replace('<table>','<div class="table-scroll"><table>').replace('</table>','</table></div>')
    css='''*{box-sizing:border-box}html{background:#fff;color:#25272a}body{margin:0;font-family:"Noto Sans CJK KR",sans-serif;font-size:16px;line-height:1.8;word-break:keep-all}main{max-width:1100px;margin:0 auto;padding:68px 48px 100px}h1{font-family:"Noto Serif CJK KR",serif;font-size:42px;line-height:1.35;margin:0 0 18px;letter-spacing:-.035em}p{margin:22px 0;max-width:960px}h1+p{font-size:13px;color:#62656a;margin:0 0 40px}strong{font-weight:700}a{color:#934121;text-underline-offset:3px}table{width:100%;border-collapse:collapse;font-size:13px;font-variant-numeric:tabular-nums;margin:20px 0}th,td{padding:12px 9px;border-bottom:1px solid #ddd;text-align:right;white-space:nowrap}th{border-bottom-color:#25272a;font-weight:600}th:first-child,td:first-child{text-align:left}.table-scroll{max-width:100%;overflow-x:auto}img{display:block;width:100%;height:auto;margin:34px 0 8px}p:has(img){max-width:none}code{font-size:.9em;font-family:monospace}::selection{background:#f1dfd6}@media(max-width:600px){main{padding:34px 20px 60px}h1{font-size:29px}body{font-size:15px}th,td{padding:10px 8px}img{min-width:660px;margin-top:24px}p:has(img){overflow-x:auto}}@media print{@page{size:A4;margin:15mm}main{padding:0;max-width:none}body{font-size:10pt;line-height:1.65}h1{font-size:23pt}table{font-size:7.3pt}th,td{padding:5px}p{margin:13px 0}table,img{break-inside:avoid}.table-scroll{overflow:visible}a{color:inherit}}'''
    document='<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>모델 역할 분담 실험 결과</title><style>'+css+'</style><main>'+content+'</main></html>'
    (directory/'report.html').write_text(mobile_document(document))
    return data


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    result=make(a.output);print(json.dumps(result['aggregate'],ensure_ascii=False,indent=2))
