##! Intel framework wiring for the homelab sensor.
##! Loaded from local.zeek. Indicators live in site/intel/master.dat, which is
##! rebuilt by /usr/local/bin/zeek-intel-update.sh (systemd timer, daily).
##!
##! master.dat is read with Input::REREAD, so an update is picked up live --
##! no Zeek restart is needed after a feed refresh.

@load base/frameworks/intel
@load frameworks/intel/seen

# Deliberately NOT loading policy/frameworks/intel/do_notice: intel.log is
# already shipped to Wazuh by the agent, and raising a notice as well would
# create a duplicate alert stream for every match.

redef Intel::read_files += {
    "/opt/zeek/share/zeek/site/intel/master.dat"
};
