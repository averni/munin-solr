# Munin-solr
-------------

Munin plugin for monitoring a multicore solr installation via mbean.
The plugin depends on python-lxml:
> sudo apt-get install python-lxml

### Setup:
===

Copy the plugin file to your munin plugins folder (ex. /usr/share/munin/plugins):

Add the following lines to the munin-node file, usually found in /etc/munin/plugin-conf.d/munin-node, adding one qpshandler for eache handler you need to monitor:

    [solr_*]
        host_port solrhost:8080 
        qpshandler_select /select


Enable numdoc check on core_1:

    ln -s /usr/share/munin/plugins/solr_.py /etc/munin/plugins/solr_numdocs_core_1


Enable qps check on the select handler for core_1

    ln -s /usr/share/munin/plugins/solr_.py /etc/munin/plugins/solr_qps_core_1_select


### Thanks:
===

Developed for www.fashionis.com
