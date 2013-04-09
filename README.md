munin-solr
-------------

Munin plugin for monitoring a multicore solr installation via mbean.
The plugin depends on python-lxml

Setup:
===

After copying the plugin file to your munin plugins folder (es. /usr/share/munin/plugins):

Add to munin-node your solr configuration and handlers:
> [solr_*]
>     host_port solrhost:8080 
>     qpshandler_select /select


ln -s /usr/share/munin/plugins/solr_.py /etc/munin/plugins/solr_numdocs_core_1

to enable numdoc check on core_1


ln -s /usr/share/munin/plugins/solr_.py /etc/munin/plugins/solr_qps_core_1_select

to enable qps check on the select handler for core_1


