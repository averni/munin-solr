# Munin-solr (4.*)
-------------

Munin plugin for monitoring a multicore solr 4.* installation via mbean.
It calls:
> http://localhost:8080/solr/admin/cores?action=STATUS&wt=json

to retrieve cores and

> http://localhost:8080/solr/corename/admin/mbeans?stats=true&wt=json
> http://localhost:8080/solr/corename/admin/system?stats=true&wt=json

to read core data and system stats

### Setup:
===

Copy the plugin file to your munin plugins folder (ex. /usr/share/munin/plugins):

Add the following lines to the munin-node file, usually found in /etc/munin/plugin-conf.d/munin-node, adding one qpshandler for each handler you need to monitor:

    [solr_*]
        env.host_port solrhost:8080 
        env.url /solr
        env.qpshandler_select /select


To enable numdoc check on core_1:

    ln -s /usr/share/munin/plugins/solr_.py /etc/munin/plugins/solr_numdocs_core_1


To enable qps and requesttimes check on a handler you have to define an alias for it in the munin-node file as from the example before installing the plugins

    ln -s /usr/share/munin/plugins/solr_.py /etc/munin/plugins/solr_qps_core_1_select
    ln -s /usr/share/munin/plugins/solr_.py /etc/munin/plugins/solr_qps_select
    ln -s /usr/share/munin/plugins/solr_.py /etc/munin/plugins/solr_requesttimes_select



### Checks available:
===

numdocs  
qps  
indexsize  
memory  
requesttimes  
documentcache  
fieldvaluecache  
filtercache  
queryresultcache  

### Requirements:
===
Python >= 2.6


### Credits:
===

Sponsored by www.fashionis.com
