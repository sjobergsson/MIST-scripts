import requests
import orionsdk
import yaml
import json
import pandas
#Email imports
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from scrapli import Scrapli

with open('/opt/scripts/switches/config.yaml') as f:
    config = yaml.load(f, Loader=yaml.FullLoader)

import logging
logging.basicConfig(format='%(asctime)s %(levelname)-8s %(message)s', filename='/opt/scripts/logs/rebootPrimary.log', level=logging.DEBUG, datefmt='%Y-%m-%d %H:%M:%S')

switch_username = config['switch']['username']
switch_password = config['switch']['password']
solarwinds_username = config['solarwinds']['username']
solarwinds_password = config['solarwinds']['password']
solarwinds_certificate = config['solarwinds']['certificate_file']

#email settings
smtp_port = config['email']['smtp_port']
smtp_server = config['email']['smtp_server']
smtp_login = config['email']['smtp_username']
smtp_password = config['email']['smtp_password']
sender_email = config['email']['sender_email']
receiver_email = config['email']['receiver_email']
message = MIMEMultipart("alternative")
message["Subject"] = "Netscript Juniper boot backup"
message["From"] = sender_email
message["To"] = receiver_email


def rebootPrimary(switch_ip):
    device = {
        "host": switch_ip,
        "auth_username": switch_username,
        "auth_password": switch_password,
        "auth_strict_key": False,
        "platform": "juniper_junos"
    }
    logging.info("Logging in to switch {}".format(switch_ip))
    try:
        conn = Scrapli(**device)
        conn.open()
        response = conn.send_command("request system configuration rescue save")
        response = conn.send_interactive(
            [
                ("request system reboot slice alternate media internal at 22",
                "Reboot the system ", False),
                ("yes", "", False)
            ]
        )
        logging.info(response.elapsed_time)
        logging.info(response.result)
        if 'Shutdown at' in response.result:
            return True
        else:
            return False
        conn.close()
    except:
        logging.warning("Couldn't reboot switch {}".format(switch_ip))
        print("Couldn't reboot switch {}".format(switch_ip))
        return False



session = requests.Session()
session.timeout = 30  # Set your timeout in seconds
logging.info("Connecting to Solarwinds")
swis = orionsdk.SwisClient("SolarWinds-Orion", solarwinds_username,
                           solarwinds_password, verify=False, session=session)
logging.info("Getting switches that need to reboot")
nodes = swis.query("SELECT NodeID, Caption, IPAddress, Status, Nodes.CustomProperties.jun_bootpart FROM Orion.Nodes WHERE Nodes.CustomProperties.jun_bootpart LIKE 'backup%'")

switches = nodes['results']
logging.debug(switches)

dict_switches = []

for switch in switches:
    if rebootPrimary(switch['IPAddress']):
        dict_switch = {
            "Switchname": switch['Caption'],
            "IP-address": switch['IPAddress'],
            "Status": "Scheduled reboot at 22:00"
        }
        dict_switches.append(dict_switch)
    else:
        dict_switch = {
            "Switchname": switch['Caption'],
            "IP-address": switch['IPAddress'],
            "Status": "Failed"
        }
        dict_switches.append(dict_switch)
logging.info(json.dumps(dict_switches, indent=2, default=str))

df_switches = pandas.DataFrame(dict_switches)

#Mail the result
# write the plain text part
text = """\
Hej
F??ljande switchar har hittats som har bootat fr??n backup-partitionen
"""
# write the HTML part
html = """\
<html>
  <body>
    <p>Hej!<br>
    <p> F??ljande switchar har hittats som har bootat fr??n backup-partitionen</p>
    <p> {} </p>
  </body>
</html>
""".format(df_switches.to_html(index=False))
# convert both parts to MIMEText objects and add them to the MIMEMultipart message
part1 = MIMEText(text, "plain")
part2 = MIMEText(html, "html")
message.attach(part1)
message.attach(part2)
# send your email
if dict_switches:
    with smtplib.SMTP(smtp_server, smtp_port) as server:
        server.sendmail(
            sender_email, receiver_email.split(','), message.as_string()
        )
else:
    logging.info("No switches found")


