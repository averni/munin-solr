#!/usr/bin/env python

import sys
import os
import httplib
import json
from pprint import pprint as pp
# http://localhost:8983/solr/core_1/admin/mbeans?stats=true

"""

Plugins configuration parameters:

[solr_*]
    host_port <host:port>
    qpshandler_<handlerlabel> <handlerpath>

    ex:
        host_port solrhost:8080 
        qpshandler_select /select

Install plugins:
    apt-get install python-lxml
    ln -s /usr/share/munin/plugins/solr_.py /etc/munin/plugins/solr_numdocs_core_1
    ln -s /usr/share/munin/plugins/solr_.py /etc/munin/plugins/solr_qps_core_1_select
"""

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
        params['params'] = {
                'handler': os.environ.get('qpshandler_%s' % handler, '/select')
        }
        if not data:
            params['core'] = ''
        else:
            params['core'] = data[0]
    elif plugname[0] ==  'indexsize':
        params['params']['core'] = params['core']
    return params

class CheckException(Exception):
    pass

class JSONReader:
    @classmethod
    def readValue(cls, struct, path):
        if not path[0] in struct:
            return -1
        obj = struct[path[0]]
        if not obj:
            return -1
        for k in path[1:]:
            obj = obj[k]
        return obj

class SolrCoresAdmin:
    def __init__(self, host):
        self.host = host
        self.data = None

    def fetchcores(self):
        uri = "/solr/admin/cores?action=STATUS&wt=json"
        conn = httplib.HTTPConnection(self.host)
        conn.request("GET", uri)
        res = conn.getresponse()
        data = res.read()
        if res.status != 200:
            raise CheckException("Cores status fetch failed: %s\n%s" %( str(res.status), res.read()))
        self.data = json.loads(data)

    def getCores(self):
        if not self.data:
            self.fetchcores()
        cores = JSONReader.readValue(self.data, ['status'])
        return cores.keys()

    def indexsize(self, core = None):
        if not self.data:
            self.fetchcores()
        if core:
            return {
                core: JSONReader.readValue(self.data, ['status', core, 'index', 'sizeInBytes'])
            }
        else:
            ret = {}
            for core in self.getCores():
                ret[core] = JSONReader.readValue(self.data, ['status', core, 'index', 'sizeInBytes'])
            return ret

class SolrCoreMBean:
    def __init__(self, host, core):
        self.host = host
        self.data = None
        self.core = core

    def _fetch(self):
        uri = "/solr/%s/admin/mbeans?stats=true&wt=json" % self.core
        conn = httplib.HTTPConnection(self.host)
        conn.request("GET", uri)
        res = conn.getresponse()
        data = res.read()
        if res.status != 200:
            raise CheckException("MBean fetch failed: %s\n%s" %( str(res.status), res.read()))
        raw_data = json.loads(data)
        data = {}
        self.data = {
            'solr-mbeans': data
        }
        key = None
        for pos, el in enumerate(raw_data['solr-mbeans']):
            if pos % 2 == 1:
                data[key] = el
            else:
                key = el

    def _read(self, path):
        if self.data is None:
            self._fetch()
        return JSONReader.readValue(self.data, path)

    def _readCache(self, cache):
        result = {}
        for key in ['lookups', 'hits', 'inserts', 'evictions', 'hitratio']:
            path = ['solr-mbeans', 'CACHE', cache, 'stats', 'cumulative_%s' % key]
            result[key] = self._read(path)
        result['size'] = self._read(['solr-mbeans', 'CACHE', cache, 'stats', 'size'])
        return result

    def getCore(self):
        return self.core

    def qps(self, handler):
        path = ['solr-mbeans', 'QUERYHANDLER', handler, 'stats', 'avgRequestsPerSecond']
        return self._read(path)

    def requesttimes(self, handler):
        times = {}
        path = ['solr-mbeans', 'QUERYHANDLER', handler, 'stats']
        for perc in ['avgTimePerRequest', '75thPcRequestTime', '99thPcRequestTime']:
            times[perc] = self._read(path + [perc])
        return times

    def numdocs(self):
        path = ['solr-mbeans', 'CORE', 'searcher', 'stats', 'numDocs']
        return self._read(path)

    def documentcache(self):
        return self._readCache('documentCache')

    def filtercache(self):
        return self._readCache('filterCache')

    def fieldvaluecache(self):
        return self._readCache('fieldValueCache')

    def queryresultcache(self):
        return self._readCache('queryResultCache')

# Graph Templates
CACHE_GRAPH_TPL = """graph_title Solr {core} {cacheType}
graph_args -l 0
graph_category solr
graph_vlabel lookups
hits.label Hits
hits.draw AREA
inserts.label Inserts
inserts.draw STACK
size.label Size
size.draw LINE2
lookups.label Lookups
lookups.draw LINE1
evictions.label Evictions
evictions.draw LINE2"""

QPSMAIN_GRAPH_TPL = """graph_title Solr {core} {handler} Request per second"
graph_args -l 0
graph_vlabel request / second
graph_category solr
qps_total.label Request count
qps_total.type LINE2
qps_total.cdef {cores_qps_cdefs}
qps_total.graph yes
{cores_qps_graphs}"""

QPSCORE_GRAPH_TPL = """qps_{core}.label {core} Request per second
qps_{core}.type GAUGE
qps_{core}.graph yes"""

REQUESTTIMES_GRAPH_TPL = """multigraph {core}_requesttimes
graph_title Solr {core} {handler} Time per request"
graph_args -l 0
graph_vlabel seconds
graph_category solr
avgtimeperrequest_{core}.label {core} Avg time per request
avgtimeperrequest_{core}.type GAUGE
avgtimeperrequest_{core}.graph yes
75thpcrequesttime_{core}.label {core} 75th perc
75thpcrequesttime_{core}.type GAUGE
75thpcrequesttime_{core}.graph yes
99thpcrequesttime_{core}.label {core} 99th perc
99thpcrequesttime_{core}.type GAUGE
99thpcrequesttime_{core}.graph yes

"""

NUMDOCS_GRAPH_TPL = """graph_title Solr Docs %s
graph_vlabel docs
docs.label Docs
graph_category solr"""

INDEXSIZE_GRAPH_TPL = """graph_args --base 1024 -l 0 --upper-limit {availableram}
graph_vlabel Bytes
graph_title Index Size
graph_category solr
graph_info Solr Index Memory Usage.
graph_order {cores}
{cores_config}
"""

INDEXSIZECORE_GRAPH_TPL = """{core}.label {core}
{core}.draw STACK""" 

class SolrMuninGraph:
    def __init__(self, hostport, solrmbean):
        self.solrcoresadmin = SolrCoresAdmin(hostport)
        self.hostport = hostport
        self.params = params

    def _getMBean(self, core):
        return SolrCoreMBean(self.hostport, core)

    def _cacheConfig(self, cacheType):
        return CACHE_GRAPH_TPL.format(core=self.params['core'], cacheType=cacheType)

    def _cacheFetch(self, cacheName, fields = None):
        fields = fields or  ['size', 'lookups', 'hits', 'inserts', 'evictions']
        results = []
        solrmbean = self._getMBean(self.params['core'])
        data = getattr(solrmbean, cacheName)()
        for label in fields:
            results.append("%s.value %s" % (label, data[label]))
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
        cores = self._getCores()
        graph = [QPSCORE_GRAPH_TPL.format(core=c) for c in cores ]
        return QPSMAIN_GRAPH_TPL.format(
            cores_qps_graphs='\n'.join(graph), 
            handler=self.params['params']['handler'], 
            core=self.params['core'], 
            cores_qps_cdefs='%s,%s' % (','.join(map(lambda x: 'qps_%s' % x, cores)),','.join(['+']*(len(cores)-1)))
        )

    def qps(self):
        results = []
        cores = self._getCores()
        for c in cores:
            mbean = self._getMBean(c)
            results.append('qps_%s.value %s' % (c, mbean.qps(self.params['params']['handler'])))
        return '\n'.join(results)

    def requesttimesConfig(self):
        cores = self._getCores()
        graphs = [REQUESTTIMES_GRAPH_TPL.format(core=c, handler=self.params['params']['handler']) for c in cores ]
        return '\n'.join(graphs)

    def requesttimes(self):
        cores = self._getCores()
        results = []
        for c in cores:
            mbean = self._getMBean(c)
            for k, time in mbean.requesttimes(self.params['params']['handler']).items():
                results.append('multigraph {core}_requesttimes'.format(core=c))
                results.append('%s_%s.value %s' % (k.lower(), c, time))
        return '\n'.join(results)

    def numdocsConfig(self):
        return NUMDOCS_GRAPH_TPL % self.solrmbean.getCore()

    def numdocs(self):
        return 'docs.value %s' % self.solrmbean.numdocs(**self.params['params'])

    def indexsizeConfig(self):
        cores = self._getCores()
        availableram = os.environ.get('availableram', 16868532224)
        graph = [ INDEXSIZECORE_GRAPH_TPL.format(core=c) for c in cores]
        return INDEXSIZE_GRAPH_TPL.format(cores=" ".join(cores), cores_config="\n".join(graph), availableram=availableram)

    def indexsize(self):
        results = []
        for c, size in self.solrcoresadmin.indexsize(**self.params['params']).items():
            results.append("%s.value %s" % (c, size))
        return "\n".join(results)

    def documentcacheConfig(self):
        return self._cacheConfig('Document Cache')

    def documentcache(self):
        return self._cacheFetch('documentcache')

    def filtercacheConfig(self):
        return self._cacheConfig('Filter Cache')

    def filtercache(self):
        return self._cacheFetch('filtercache')

    def fieldvaluecacheConfig(self):
        return self._cacheConfig('Field Value Cache')

    def fieldvaluecache(self):
        return self._cacheFetch(sys._getframe().f_code.co_name)

    def queryresultcacheConfig(self):
        return self._cacheConfig('Query Cache')

    def queryresultcache(self):
        return self._cacheFetch('queryresultcache')

if __name__ == '__main__':
    params = parse_params()
    SOLR_HOST_PORT = os.environ.get('host_port', 'localhost:8080').replace('http://', '')
    mb = SolrMuninGraph(SOLR_HOST_PORT, params)
    if hasattr(mb, params['op']):
        print getattr(mb,  params['op'])(params['type'])

