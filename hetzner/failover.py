import re
import subprocess

from hetzner import RobotError

__all__ = ['Failover', 'FailoverManager']


class Failover(object):
    ip = None
    server_ip = None
    server_number = None
    active_server_ip = None

    def __repr__(self):
        return "%s (destination: %s, booked on %s (%s))" % (
            self.ip, self.active_server_ip, self.server_number, self.server_ip)

    def __init__(self, data):
        for attr, value in data.items():
            if hasattr(self, attr):
                setattr(self, attr, value)


class FailoverManager(object):
    def __init__(self, conn, servers):
        self.conn = conn
        self.servers = servers

    def list(self):
        failovers = {}
        try:
            ips = self.conn.get('/failover')
        except RobotError as err:
            if err.status == 404:
                return failovers
            else:
                raise
        for ip in ips:
            failover = Failover(ip.get('failover'))
            failovers[failover.ip] = failover
        return failovers

    def set(self, ip, dest_list):
        failovers = self.list()
        if ip not in failovers.keys():
            raise RobotError(
                "Invalid IP address '%s'. Failover IP addresses are %s"
                % (ip, failovers.keys()))
        failover = failovers.get(ip)
        if failover.active_server_ip in dest_list:
            raise RobotError(
                "%s is already the active destination of failover IP %s"
                % (dest_list.join(', '), ip))
        available_dests = set([s.ip for s in list(self.servers)])
        if len(available_dests.intersection(set(dest_list))) == 0:
            raise RobotError(
                "Invalid destination '%s'. "
                "The destination is not in your server list: %s"
                % (dest_list.join(', '), available_dests))
        result = self.conn.post('/failover/%s'
                                % ip, {'active_server_ip': dest_list.join(', ')})
        return Failover(result.get('failover'))

    def monitor(self):
        """Check if container with failover IP is running on host
           and if IP is not mapped to host change settings
        """
        msgs = []
        failovers = self.list()
        if len(failovers) > 0:
            ips = self._get_active_ips()
            host_ips = self._get_host_ip().split(' ')
            for failover_ip, failover in failovers.items():
                if failover_ip in ips and failover.active_server_ip not in host_ips:
                    new_failover = self.set(failover_ip, host_ips)
                    if new_failover:
                        msgs.append("Failover IP successfully assigned to new"
                                    " destination")
                        msgs.append(str(failover))
        return msgs

    def _get_active_ips(self):
        ips = []
        try:
            out = subprocess.check_output(["lxc-ls", "--active", "-fF", "IPV4"])
        except subprocess.CalledProcessError as e:
            raise RobotError(str(e))
        except Exception as e:
            raise RobotError(str(e))
        else:
            [ips.extend([ip.strip() for ip in line.strip().split(',')])
             for line in out.split('\n')
             if re.search(r'\d+\.\d+\.\d+\.\d', line)]
            return ips

    def _get_host_ip(self):
        try:
            host_ip = subprocess.check_output(["hostname", "--ip-address"])
        except subprocess.CalledProcessError as e:
            raise RobotError(str(e))
        except Exception as e:
            raise RobotError(str(e))
        else:
            return host_ip.strip()

