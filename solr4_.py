#!/usr/bin/env python
#
# Copyright (c) 2013, Antonio Verni, me.verni@gmail.com
# 
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and associated documentation files (the "Software"),
# to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense,
# and/or sell copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included
# in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
# OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.
#
# Solr 4.* munin graph plugin
# Project repo: https://github.com/averni/munin-solr
#
# Plugin configuration parameters:
#
# [solr4_*]
#    env.solr4_host_port <host:port>
#    env.solr4_url <default /solr>
#    env.solr4_qpshandler_<handlerlabel> <handlerpath>
#    env.solr4_qpshandler_<handlerlabel>_usealias <1|0 default 0>
#
# Example:
# [solr4_*]
#    env.solr4_host_port solrhost:8080 
#    env.solr4_url /solr
#    env.solr4_qpshandler_select /select
#
# Install plugins:
#    ln -s /usr/share/munin/plugins/solr4_.py /etc/munin/plugins/solr_numdocs_core_1
#    ln -s /usr/share/munin/plugins/solr4_.py /etc/munin/plugins/solr_requesttimes_select
#    ln -s /usr/share/munin/plugins/solr4_.py /etc/munin/plugins/solr_qps
#    ln -s /usr/share/munin/plugins/solr4_.py /etc/munin/plugins/solr_qps_core_1_select
#    ln -s /usr/share/munin/plugins/solr4_.py /etc/munin/plugins/solr_indexsize
#    ln -s /usr/share/munin/plugins/solr4_.py /etc/munin/plugins/solr_memory
#
#


import sys
import os
import httplib
import json
import base64

# core alias support, added to handle core names with dot
def load_alias(cores_alias):
    if not cores_alias:
        return {}
    alias = [core_alias.split(':') for core_alias in cores_alias.split(' ')]
    dict_alias = dict(alias)
    dict_alias.update([(a[1], a[0]) for a in alias])
    return dict_alias

URIS = {
    'CORES': "admin/cores?action=STATUS&wt=json",
    'CORE_MBEAN': "admin/mbeans?stats=true&wt=json",
    'CORE_SYSTEM':"admin/system?stats=true&wt=json"
} 

CORE_ALIAS =  load_alias(os.environ.get('solr4_cores_alias'))
def core_alias(core_alias):
    if isinstance(core_alias, list):
        return [CORE_ALIAS.get(c, c) for c in core_alias]
    return CORE_ALIAS.get(core_alias, core_alias)

def parse_bool(text):
    return text and text[0].lower() not in ['f', '0']

def parse_params():
    plugname = os.path.basename(sys.argv[0]).split('_', 2)[1:]
    params = {
        'type': plugname[0],
        'op': 'config' if sys.argv[-1] == 'config' else 'fetch',
        'core': plugname[1] if len(plugname) > 1 else '',
        'params': {}
    }
    if plugname[0] in[ 'qps', 'requesttimes']:
        data = params['core'].rsplit('_', 1)
        handler = data.pop()
        usealias = parse_bool(os.environ.get('solr4_qpshandler_%s_usealias' % handler, 'f')),
        handlername = os.environ.get('solr4_qpshandler_%s' % handler, 'standard')
        params['params'] = {
                'handler': handlername,
                'handleralias': handler if usealias else handlername
        }
        if not data:
            params['core'] = ''
        else:
            params['core'] = data[0]
    elif plugname[0] ==  'indexsize':
        params['params']['core'] = params['core']
    if params['core'] in CORE_ALIAS:
        params['core'] = CORE_ALIAS[params['core']]
        if 'core' in params['params']:
            params['params']['core'] = CORE_ALIAS[params['params']['core']]
    return params

#############################################################################
# Datasources

class CheckException(Exception):
    pass

def readPath(struct, path, convert=None, default=-1):
    if not path[0] in struct or not struct[path[0]]:
        return default 
    obj = struct[path[0]]
    for k in path[1:]:
        obj = obj.get(k)
        if obj is None:
            obj = default
            break
    if convert:
        obj = convert(obj)
    return obj

def HTTPGetJson(host, url):
    conn = httplib.HTTPConnection(host)
    headers = {}
    SOLR_AUTH  = os.environ.get('solr4_auth')
    if SOLR_AUTH:
        headers["Authorization"] = "Basic %s" % base64.encodestring(SOLR_AUTH).replace('\n', '')
    conn.request("GET", url, headers=headers)
    res = conn.getresponse()
    if res.status != 200:
        raise CheckException("%s %s fetch failed: %s\n%s" %( host, url, str(res.status), res.read()))
    try:
        return json.loads(res.read())
    except ValueError, ex:
        raise CheckException("%s %s response parsing failed: %s\n%s" %( host, url, ex, res.read()))

class SolrCoresAdmin:
    def __init__(self, host, solrurl):
        self.host = host
        self.solrurl = solrurl
        self.data = self._fetchCores()

    def _fetchCores(self):
        uri = os.path.join(self.solrurl, URIS['CORES'])
        return HTTPGetJson(self.host, uri)

    def getCores(self):
        cores = readPath(self.data, ['status'])
        return cores.keys()

    def indexsize(self, core = None):
        result = {}
        if core:
            result[core] =  readPath(self.data, ['status', core, 'index', 'sizeInBytes'])
        else:
            for core in self.getCores():
                result[core] = readPath(self.data, ['status', core, 'index', 'sizeInBytes'])
        return result

class SolrCoreMBean:
    def __init__(self, host, solrurl, core):
        self.host = host
        self.core = core
        self.solrurl = solrurl
        self.data = {
            'solr-mbeans': self._fetchMBeans(),
            'system': self._fetchSystem()
        }

    def _fetchMBeans(self):
        uri = os.path.join(self.solrurl, self.core, URIS['CORE_MBEAN'])
        raw_data = HTTPGetJson(self.host, uri)
        data = {}
        key = None
        for pos, el in enumerate(raw_data['solr-mbeans']):
            if pos % 2 == 1:
                data[key] = el
            else:
                key = el
        return data

    def _fetchSystem(self):
        uri = os.path.join(self.solrurl, self.core, URIS['CORE_SYSTEM'])
        return HTTPGetJson(self.host, uri)

    def _readInt(self, path):
        return self._read(path, int)

    def _readFloat(self, path):
        return self._read(path, float)

    def _read(self, path, convert = None):
        return readPath(self.data, path, convert)

    def _readCache(self, cache):
        result = {}
        for key, ftype in [('lookups', int), ('hits', int), ('inserts', int), ('evictions', int), ('hitratio', float)]:
            path = ['solr-mbeans', 'CACHE', cache, 'stats', 'cumulative_%s' % key]
            result[key] = self._read(path, ftype)
        result['size'] = self._readInt(['solr-mbeans', 'CACHE', cache, 'stats', 'size'])
        return result

    def getCore(self):
        return self.core

    def requestcount(self, handler):
        path = ['solr-mbeans', 'QUERYHANDLER', handler, 'stats', 'requests']
        return self._readInt(path)

    def requesttimeouts(self, handler):
        path = ['solr-mbeans', 'QUERYHANDLER', handler, 'stats', 'timeouts']
        return self._readInt(path)

    def requesterrors(self, handler):
        path = ['solr-mbeans', 'QUERYHANDLER', handler, 'stats', 'errors']
        return self._readInt(path)

    def qps(self, handler):
        path = ['solr-mbeans', 'QUERYHANDLER', handler, 'stats', 'avgRequestsPerSecond']
        return self._readFloat(path)

    def requesttimes(self, handler):
        times = {}
        path = ['solr-mbeans', 'QUERYHANDLER', handler, 'stats']
        for perc in ['avgTimePerRequest', '75thPcRequestTime', '99thPcRequestTime']:
            times[perc] = self._read(path + [perc], float)
        return times

    def numdocs(self):
        path = ['solr-mbeans', 'CORE', 'searcher', 'stats', 'numDocs']
        return self._readInt(path)

    def documentcache(self):
        return self._readCache('documentCache')

    def filtercache(self):
        return self._readCache('filterCache')

    def fieldvaluecache(self):
        return self._readCache('fieldValueCache')

    def queryresultcache(self):
        return self._readCache('queryResultCache')

    def memory(self):
        data = self._read(['system', 'jvm', 'memory', 'raw'])
        if 'used%' in data:
            del data['used%']
        for k in data.keys():
            data[k] = int(data[k])
        return data

#############################################################################
# Graph Templates

CACHE_GRAPH_TPL = """multigraph solr_{core}_{cacheType}_hit_rates
graph_category solr
graph_title Solr {core} {cacheName} Hit rates
graph_order lookups hits inserts
graph_scale no
graph_vlabel Hit Rate
graph_args -u 100 --rigid
lookups.label Cache lookups
lookups.graph no
lookups.min 0
lookups.type DERIVE
inserts.label Cache misses
inserts.min 0
inserts.draw STACK
inserts.cdef inserts,lookups,/,100,*
inserts.type DERIVE
hits.label Cache hits
hits.min 0
hits.draw AREA
hits.cdef hits,lookups,/,100,*
hits.type DERIVE

multigraph solr_{core}_{cacheType}_size
graph_title Solr {core} {cacheName} Size
graph_args -l 0
graph_category solr
graph_vlabel Size
size.label Size
size.draw AREA
evictions.label Evictions/s
evictions.draw LINE2
evictions.type DERIVE
"""

QPSMAIN_GRAPH_TPL = """graph_title Solr {core} {handler} Request per second
graph_args --base 1000 -r --lower-limit 0
graph_scale no
graph_vlabel request / second
graph_category solr
graph_period second
graph_order {gorder}
{cores_qps_graphs}"""

QPSCORE_GRAPH_TPL = """qps_{core}_{handler}.label {core} Request per second
qps_{core}_{handler}.draw {gtype}
qps_{core}_{handler}.type DERIVE
qps_{core}_{handler}.colour 008000
qps_{core}_{handler}.min 0
qps_{core}_{handler}.graph yes
timeouts_{core}_{handler}.label {core} Timouts per second
timeouts_{core}_{handler}.draw {gtype}
timeouts_{core}_{handler}.type DERIVE
timeouts_{core}_{handler}.colour FFA500
timeouts_{core}_{handler}.min 0
timeouts_{core}_{handler}.graph yes
errors_{core}_{handler}.label {core} Errors per second
errors_{core}_{handler}.draw {gtype}
errors_{core}_{handler}.type DERIVE
errors_{core}_{handler}.colour FF0000
errors_{core}_{handler}.min 0
errors_{core}_{handler}.graph yes"""

REQUESTTIMES_GRAPH_TPL = """multigraph solr_requesttimes_{core}_{handler}
graph_title Solr {core} {handler} Time per request
graph_args -l 0
graph_vlabel millis
graph_category solr
savgtimeperrequest_{core}.label {core} Avg time per request
savgtimeperrequest_{core}.type GAUGE
savgtimeperrequest_{core}.graph yes
s75thpcrequesttime_{core}.label {core} 75th perc
s75thpcrequesttime_{core}.type GAUGE
s75thpcrequesttime_{core}.graph yes
s99thpcrequesttime_{core}.label {core} 99th perc
s99thpcrequesttime_{core}.type GAUGE
s99thpcrequesttime_{core}.graph yes
"""

NUMDOCS_GRAPH_TPL = """graph_title Solr Docs %s
graph_vlabel docs
docs.label Docs
graph_category solr"""

INDEXSIZE_GRAPH_TPL = """graph_args --base 1024 -l 0 
graph_vlabel Bytes
graph_title Index Size
graph_category solr
graph_info Solr Index Size.
graph_order {cores}
{cores_config}
xmx.label Xmx
xmx.colour ff0000
"""

INDEXSIZECORE_GRAPH_TPL = """{core}.label {core}
{core}.draw STACK""" 

MEMORYUSAGE_GRAPH_TPL = """graph_args --base 1024 -l 0 --upper-limit {availableram}
graph_vlabel Bytes
graph_title Solr memory usage
graph_category solr
graph_info Solr Memory Usage.
used.label Used
max.label Max
max.colour ff0000
"""

#############################################################################
# Graph managment

class SolrMuninGraph:
    def __init__(self, hostport, solrurl, params):
        self.solrcoresadmin = SolrCoresAdmin(hostport, solrurl)
        self.hostport = hostport
        self.solrurl = solrurl
        self.params = params

    def _getMBean(self, core):
        return SolrCoreMBean(self.hostport, self.solrurl, core)

    def _cacheConfig(self, cacheType, cacheName):
        core = core_alias(self.params['core'])
        return CACHE_GRAPH_TPL.format(core=core, cacheType=cacheType, cacheName=cacheName)

    def _format4Value(self, value):
        if isinstance(value, basestring):
            return "%s"
        if isinstance(value, int):
            return "%d"
        if isinstance(value, float):
            return "%.6f"
        return "%s"

    def _cacheFetch(self, cacheType, fields = None):
        fields = fields or ['size', 'lookups', 'hits', 'inserts', 'evictions']
        hits_fields = ['lookups', 'hits', 'inserts']
        size_fields = ['size', 'evictions']
        results = []
        solrmbean = self._getMBean(self.params['core'])
        data = getattr(solrmbean, cacheType)()
        core = core_alias(self.params['core'])
        results.append('multigraph solr_{core}_{cacheType}_hit_rates'.format(core=core, cacheType=cacheType))
        for label in hits_fields:
            vformat = self._format4Value(data[label])
            results.append(("%s.value " + vformat) % (label, data[label]))
        results.append('multigraph solr_{core}_{cacheType}_size'.format(core=core, cacheType=cacheType))
        for label in size_fields:
            results.append("%s.value %d" % (label, data[label]))
        return "\n".join(results)

    def config(self, mtype):
        if not mtype or not hasattr(self, '%sConfig' % mtype):
            raise CheckException("Unknown check %s" % mtype)
        return getattr(self, '%sConfig' % mtype)()

    def fetch(self, mtype):
        if not hasattr(self, params['type']):
            return None
        return getattr(self, params['type'])()

    def _getCores(self):
        if self.params['core']:
            cores = [self.params['core']]
        else:
            cores = sorted(self.solrcoresadmin.getCores())
        return cores

    def qpsConfig(self):
        cores = core_alias(self._getCores())
        graph = [QPSCORE_GRAPH_TPL.format(core=c, handler=self.params['params']['handleralias'], gtype='LINESTACK1') for pos,c in enumerate(cores) ]
        return QPSMAIN_GRAPH_TPL.format(
            cores_qps_graphs='\n'.join(graph), 
            handler=self.params['params']['handleralias'], 
            core = core_alias(self.params['core']), 
            cores_qps_cdefs='%s,%s' % (','.join(map(lambda x: 'qps_%s' % x, cores)),','.join(['+']*(len(cores)-1))), 
            gorder=','.join(cores)
        )

    def qps(self):
        results = []
        cores = self._getCores()
        for c in cores:
            mbean = self._getMBean(c)
            c = core_alias(c)
            results.append('qps_%s_%s.value %d' % (c, self.params['params']['handleralias'], mbean.requestcount(self.params['params']['handler'])))
            results.append('timeouts_%s_%s.value %d' % (c, self.params['params']['handleralias'], mbean.requesttimeouts(self.params['params']['handler'])))
            results.append('errors_%s_%s.value %d' % (c, self.params['params']['handleralias'], mbean.requesterrors(self.params['params']['handler'])))
        return '\n'.join(results)

    def requesttimesConfig(self):
        graphs = [REQUESTTIMES_GRAPH_TPL.format(core=c, handler=self.params['params']['handleralias']) for c in core_alias(self._getCores()) ]
        return '\n'.join(graphs)

    def requesttimes(self):
        cores = self._getCores()
        results = []
        for c in cores:
            mbean = self._getMBean(c)
            c = core_alias(c)
            results.append('multigraph solr_requesttimes_{core}_{handler}'.format(core=c, handler=self.params['params']['handleralias']))
            for k, time in mbean.requesttimes(self.params['params']['handler']).items():
                results.append('s%s_%s.value %.5f' % (k.lower(), c, time))
        return '\n'.join(results)

    def numdocsConfig(self):
        return NUMDOCS_GRAPH_TPL % core_alias(self.params['core'])

    def numdocs(self):
        mbean = self._getMBean(self.params['core'])
        return 'docs.value %d' % mbean.numdocs(**self.params['params'])

    def indexsizeConfig(self):
        cores = core_alias(self._getCores())
        graph = [ INDEXSIZECORE_GRAPH_TPL.format(core=c) for c in cores]
        return INDEXSIZE_GRAPH_TPL.format(cores=" ".join(cores), cores_config="\n".join(graph))

    def indexsize(self):
        results = []
        for c, size in self.solrcoresadmin.indexsize(**self.params['params']).items():
            results.append("%s.value %d" % (core_alias(c), size))
        cores = self._getCores()
        mbean = self._getMBean(cores[0])
        memory = mbean.memory()
        results.append('xmx.value %d' % memory['max'])
        return "\n".join(results)

    def memoryConfig(self):
        cores = self._getCores()
        mbean = self._getMBean(cores[0])
        memory = mbean.memory()
        return MEMORYUSAGE_GRAPH_TPL.format(availableram=memory['max'] * 1.05)

    def memory(self):
        results = []
        cores = self._getCores()
        mbean = self._getMBean(cores[0])
        memory = mbean.memory()
        return '\n'.join(['used.value %d' % memory['used'], 'max.value %d' % memory['max']])

    def documentcacheConfig(self):
        return self._cacheConfig('documentcache', 'Document Cache')

    def documentcache(self):
        return self._cacheFetch('documentcache')

    def filtercacheConfig(self):
        return self._cacheConfig('filtercache', 'Filter Cache')

    def filtercache(self):
        return self._cacheFetch('filtercache')

    def fieldvaluecacheConfig(self):
        return self._cacheConfig('fieldvaluecache', 'Field Value Cache')

    def fieldvaluecache(self):
        return self._cacheFetch('fieldvaluecache')

    def queryresultcacheConfig(self):
        return self._cacheConfig('queryresultcache', 'Query Cache')

    def queryresultcache(self):
        return self._cacheFetch('queryresultcache')

if __name__ == '__main__':
    params = parse_params()
    SOLR_HOST_PORT = os.environ.get('solr4_host_port', 'localhost:8080').replace('http://', '')
    SOLR_URL  = os.environ.get('solr4_url', '/solr')
    if SOLR_URL[0] != '/':
        SOLR_URL = '/' + SOLR_URL 
    mb = SolrMuninGraph(SOLR_HOST_PORT, SOLR_URL, params)
    if hasattr(mb, params['op']):
        print getattr(mb,  params['op'])(params['type'])

