"""Read the Fable subscription limit; never enable credits or make model calls."""
import json
from pathlib import Path
import urllib.request
from zoneinfo import ZoneInfo
from datetime import datetime


def quota():
    credentials=json.loads((Path.home()/'.claude/.credentials.json').read_text())
    token=credentials['claudeAiOauth']['accessToken']
    request=urllib.request.Request('https://api.anthropic.com/api/oauth/usage',headers={
        'Authorization':'Bearer '+token,'anthropic-beta':'oauth-2025-04-20',
        'User-Agent':'claude-code/2.1.270'})
    with urllib.request.urlopen(request,timeout=15) as response:data=json.load(response)
    limits=[]
    for limit in data.get('limits',[]):
        scope=limit.get('scope') or {}
        model=scope.get('model') or {}
        if 'fable' in str(model.get('display_name','')).lower():
            reset=limit.get('resets_at')
            limits.append({'percent':limit.get('percent'),'active':limit.get('is_active'),
                           'resets_at_kst':datetime.fromisoformat(reset).astimezone(ZoneInfo('Asia/Seoul')).isoformat() if reset else None})
    return {'fable_limits':limits,'extra_usage_enabled':data.get('extra_usage',{}).get('is_enabled',False)}


if __name__=='__main__':
    print(json.dumps(quota(),ensure_ascii=False,indent=2))
