"""Independent contract arithmetic, synthetic inputs only; no repository imports."""
import json
from fractions import Fraction as F

def episodes(observed):
    wealth = [F(100), *map(F, observed)]
    out = []
    for p in range(len(wealth) - 1):
        if wealth[p] < max(wealth[:p + 1]) or wealth[p + 1] >= wealth[p]:
            continue
        recovery = next((i for i in range(p + 1, len(wealth)) if wealth[i] >= wealth[p]), None)
        end = len(wealth) - 1 if recovery is None else recovery
        out.append({'peak_index': p, 'recovery_index': recovery, 'observed_sessions': end - p,
                    'censored': recovery is None})
    return out

def measure(values):
    e = episodes(values)
    maximum = max((x['observed_sessions'] for x in e), default=0)
    return {'episodes': e, 'maximum_observed_sessions': maximum,
            'any_open_episode': any(x['censored'] for x in e),
            'maximizing_observed_episode_open': any(x['censored'] and x['observed_sessions'] == maximum for x in e)}

cases = {
    'earlier_recovered_max_then_short_open': [90,85,90,100,95],
    'open_episode_is_longest': [90,100,80,85,90],
    'all_recovered_control': [90,85,90,100],
    'equal_peak_resets_origin': [100,100,90,100],
    'tied_open_and_recovered_observed_lengths': [90,100,90,95],
    'flat_control': [100,100,100],
    'prefix_then_early_recovery': [90,85,90,100,95,100],
    'same_prefix_then_late_recovery': [90,85,90,100,95,95,95,95,95,100],
}
repeats = []
for repeat in range(2):
    result = {name: measure(v) for name,v in cases.items()}
    assert result['earlier_recovered_max_then_short_open']['maximum_observed_sessions'] == 4
    assert result['earlier_recovered_max_then_short_open']['any_open_episode']
    assert not result['earlier_recovered_max_then_short_open']['maximizing_observed_episode_open']
    assert result['open_episode_is_longest']['maximum_observed_sessions'] == 3
    assert not result['all_recovered_control']['any_open_episode']
    assert result['flat_control']['maximum_observed_sessions'] == 0
    assert result['equal_peak_resets_origin']['maximum_observed_sessions'] == 2
    assert result['prefix_then_early_recovery']['maximum_observed_sessions'] == 4
    assert result['same_prefix_then_late_recovery']['maximum_observed_sessions'] == 6
    repeats.append(result)
print(json.dumps({'scope':'independent synthetic mathematical oracle, not untouched product behavior',
                 'cases':cases,'repeats':repeats,'passed':True},indent=2))
