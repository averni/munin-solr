#!/usr/bin/env python

import sys
import os
import httplib
from lxml import etree
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
        'op': sys.argv[-1] == 'config' and 'config' or 'fetch',
        'core': plugname[1],
        'params': {}
    }
    if plugname[0] == 'qps':
        data = params['core'].rsplit('_', 1)
        params['params'] = {
                'handler': os.environ.get('qpshandler_%s' % data[-1], '/select')
        }
        params['core'] = data[0]
    return params

class SolrCoreMBeanException(Exception):
    pass

class SolrCoreMBean:
    def __init__(self, host, core):
        self.host = host
        self.mbean_xml = None
        self.core = core

    def _fetch(self):
        uri = "/solr/%s/admin/mbeans?stats=true" % self.core
        conn = httplib.HTTPConnection(self.host)
        conn.request("GET", uri)
        res = conn.getresponse()
        data = res.read()
        if res.status != 200:
            raise SolrCoreMBeanException("MBean fetch failed: " + str(res.status) + ":" + res.read())
        self.mbean_xml = etree.fromstring(data)

    def _read(self, path):
        if self.mbean_xml is None:
            self._fetch()
        element = self.mbean_xml.xpath(path)
        if element:
            return element[0].text.strip()
        return -1

    def _readCache(self, cache):
        result = {}
        for key in ['lookups', 'hits', 'inserts', 'evictions', 'hitratio']:
            path = "//lst[@name='solr-mbeans']/lst[@name='CACHE']/lst[@name='%s']/lst[@name='stats']/*[@name='cumulative_%s']" % (cache, key)
            result[key] = self._read(path)
        result['size'] = self._read("//lst[@name='solr-mbeans']/lst[@name='CACHE']/lst[@name='%s']/lst[@name='stats']/*[@name='size']" % cache)
        return result

    def getCore(self):
        return self.core

    def qps(self, handler):
        path = "//lst[@name='solr-mbeans']/lst[@name='QUERYHANDLER']/lst[@name='%s']/lst[@name='stats']/*[@name='avgRequestsPerSecond']" % handler
        return self._read(path)

    def numdocs(self):
        path = "//lst[@name='solr-mbeans']/lst[@name='CORE']/lst[@name='searcher']/lst[@name='stats']/int[@name='numDocs']"
        return self._read(path)

#    def numDocsConfig(self):

    def documentcache(self):
        return self._readCache('documentCache')

    def filtercache(self):
        return self._readCache('filterCache')

    def fieldvaluecache(self):
        return self._readCache('fieldValueCache')

    def queryresultcache(self):
        return self._readCache('queryResultCache')


class SolrMuninGraph:
    def __init__(self, hostport, solrmbean):
        self.solrmbean = SolrCoreMBean(hostport, params['core'])
        self.params = params

    def _cacheConfig(self, cacheType):
        return """graph_title Solr %s
graph_args -l 0
graph_category search
graph_vlabel size
size.label Size
size.draw AREA
lookups.label Lookups
lookups.draw STACK
hits.label Hits
hits.draw STACK
inserts.label Inserts
inserts.draw STACK
evictions.label Evictions
evictions.draw STACK""" % cacheType

    def _cacheFetch(self, cacheName):
        results = []
        data = getattr(self.solrmbean, cacheName)()
        for label in ['size', 'lookups', 'hits', 'inserts', 'evictions']:
            results.append("%s.value %s" % (label, data[label]))
        return "\n".join(results)


    def config(self, mtype):
        if not mtype or not hasattr(self, '%sConfig' % mtype):
            raise SolrCoreMBeanException("Unknown check %s" % mtype)
        return getattr(self, '%sConfig' % mtype)()

    def qpsConfig(self):
        return """graph_title Solr %s %s Queries per second"
graph_args -l 0
graph_vlabel qps
graph_category search
qps.label Queries per second""" % (self.solrmbean.getCore(), self.params['params']['handler'])

    def qps(self):
        return 'qps.value %s' % getattr(self.solrmbean, sys._getframe().f_code.co_name)(**self.params['params'])

    def numdocsConfig(self):
        return """graph_title Solr Docs %s
graph_vlabel docs
docs.label Docs
graph_category search""" % self.solrmbean.getCore()

    def numdocs(self):
        return 'docs.value %s' % getattr(self.solrmbean, sys._getframe().f_code.co_name)()

    def documentcacheConfig(self):
        return self._cacheConfig('Document Cache')

    def documentcache(self):
        return self._cacheFetch(sys._getframe().f_code.co_name)

    def filtercacheConfig(self):
        return self._cacheConfig('Filter Cache')

    def filtercache(self):
        return self._cacheFetch(sys._getframe().f_code.co_name)

    def fieldvaluecacheConfig(self):
        return self._cacheConfig('Field Value Cache')

    def fieldvaluecache(self):
        return self._cacheFetch(sys._getframe().f_code.co_name)

    def queryresultcacheConfig(self):
        return self._cacheConfig('Query Cache')

    def queryresultcache(self):
        return self._cacheFetch(sys._getframe().f_code.co_name)

if __name__ == '__main__':
    params = parse_params()
    SOLR_HOST_PORT = os.environ.get('host_port', 'localhost:8080').replace('http://', '')
    mb = SolrMuninGraph(SOLR_HOST_PORT, params)
    if params['op'] == 'config':
        print mb.config(params['type'])
    else:
        print getattr(mb, params['type'])()

