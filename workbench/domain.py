import re
def leaf_key(label):
    m=re.fullmatch(r'(\d+)([rv])',label)
    if m:return ['leaf',int(m[1]),m[2]]
    m=re.fullmatch(r'(fold|ins)(\d+)',label)
    if m:return [m[1],int(m[2])]
    raise ValueError('叶序格式不明')
def coverage(expected,observed):
    counts={x:observed.count(x) for x in set(observed)}
    return {'missing':sorted(set(expected)-set(observed)),'duplicate':sorted(x for x,n in counts.items() if n>1),'extra':sorted(set(observed)-set(expected))}
def licensed(grant,use,until):
    return use in grant['uses'] and grant.get('until','')>=until
TOOLS={'leaf_key':leaf_key,'coverage':coverage,'licensed':licensed}
