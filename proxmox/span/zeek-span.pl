#!/usr/bin/perl
# Proxmox hookscript: re-apply the Zeek span mirror after the OPNsense VM starts.
# The VM's tap interface is destroyed and recreated on every start, taking the tc
# mirror with it. Attach with:  qm set <FW_VMID> --hookscript local:snippets/zeek-span.pl
# Settings come from /etc/default/zeek-span (FW_VMID, MIRROR_SRC, MIRROR_DST).
use strict; use warnings;
my ($vmid, $phase) = @ARGV;
exit 0 unless defined $phase && $phase eq 'post-start';

my $want = '';
if (open(my $fh, '<', '/etc/default/zeek-span')) {
    while (<$fh>) { $want = $1 if /^\s*FW_VMID=(\d+)/; }
    close $fh;
}
exit 0 unless $want ne '' && defined $vmid && $vmid eq $want;

# Run detached so VM start is never blocked; the script waits for the interfaces itself.
my $pid = fork();
if (defined $pid && $pid == 0) {
    exec('/usr/local/sbin/zeek-span-apply.sh') or exit 1;
}
exit 0;
