#!/usr/bin/perl
# Re-apply the Zeek span mirror after VM200 (OPNsense) starts.
#
# WHY THIS EXISTS
#   Zeek (CT206) captures on veth206i1, fed by two tc mirred filters on tap200i1 --
#   OPNsense's LAN tap. Those filters were originally added by hand at the shell. tc rules
#   are runtime-only, and tap200i1 is DESTROYED AND RECREATED every time VM200 restarts.
#   So the sensor feed silently disappeared on any VM200 restart or pve reboot.
#
#   The dangerous part is the detection gap: Zeek's capture_loss is computed from TCP ACKs
#   for data it never saw. A COMPLETELY blind Zeek sees no ACKs either, so it reports 0%
#   loss and rule 100713 (SENSOR BLIND) stays silent -- precisely when the sensor is dead.
#   Loud when degraded, silent when destroyed. This script removes that failure mode.
#
# Idempotent by construction: it deletes both clsact hooks before re-adding, so running it
# twice cannot double-mirror (a duplicated egress filter sends every packet to Zeek twice).
use strict; use warnings;
my ($vmid, $phase) = @ARGV;
exit 0 unless $vmid && $vmid eq '200';
exit 0 unless $phase && $phase eq 'post-start';

my $DEV = 'tap200i1';
my $MIRROR = 'veth206i1';

for (my $i = 0; $i < 30; $i++) { last if -e "/sys/class/net/$DEV"; sleep 1; }
unless (-e "/sys/class/net/$DEV") {
    warn "vm200-span: $DEV never appeared - Zeek has NO traffic feed\n"; 
    system("logger -t vm200-span -p daemon.err -- 'span NOT applied: $DEV absent - Zeek is blind'");
    exit 0;
}
unless (-e "/sys/class/net/$MIRROR") {
    warn "vm200-span: $MIRROR absent (is CT206 running?) - skipping\n";
    system("logger -t vm200-span -p daemon.err -- 'span NOT applied: $MIRROR absent - Zeek is blind'");
    exit 0;
}

system("tc qdisc add dev $DEV clsact 2>/dev/null");
system("tc filter del dev $DEV ingress 2>/dev/null");
system("tc filter del dev $DEV egress 2>/dev/null");
system("tc filter add dev $DEV ingress matchall action mirred egress mirror dev $MIRROR");
system("tc filter add dev $DEV egress  matchall action mirred egress mirror dev $MIRROR");

my $in  = `tc filter show dev $DEV ingress 2>/dev/null | grep -c mirred`; chomp $in;
my $out = `tc filter show dev $DEV egress  2>/dev/null | grep -c mirred`; chomp $out;
if ($in == 1 && $out == 1) {
    system("logger -t vm200-span -p daemon.notice -- 'span re-applied: $DEV ingress+egress -> $MIRROR'");
} else {
    system("logger -t vm200-span -p daemon.err -- 'span WRONG: ingress=$in egress=$out (expected 1 and 1)'");
}
exit 0;
