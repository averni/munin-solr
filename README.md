# Munin-solr (4.*)
-------------

Munin plugin for monitoring a multicore solr 4.* installation via mbean.
It calls:
> http://localhost:8080/solr/admin/cores?action=STATUS&wt=json

> http://localhost:8080/solr/core_1/admin/mbeans?stats=true
to retrieve cores and cores data

### Setup:
===

Copy the plugin file to your munin plugins folder (ex. /usr/share/munin/plugins):

Add the following lines to the munin-node file, usually found in /etc/munin/plugin-conf.d/munin-node, adding one qpshandler for each handler you need to monitor:

    [solr_*]
        host_port solrhost:8080 
        qpshandler_select /select
        availableram: 3221225472


To enable numdoc check on core_1:

    ln -s /usr/share/munin/plugins/solr_.py /etc/munin/plugins/solr_numdocs_core_1


To enable qps check on the select handler for core_1

    ln -s /usr/share/munin/plugins/solr_.py /etc/munin/plugins/solr_qps_core_1_select


### Checks available:
===

numdocs
qps
indexsize
requesttimes
documentcache
fieldvaluecache
filtercache
queryresultcache


### Credits:
===

Developed for www.fashionis.com
