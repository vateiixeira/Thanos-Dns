import boto3
from decouple import config
import json
import codecs
import requests
from datetime import date, datetime
import logging
import botocore

logging.basicConfig(filename=config('LOG_PATH'), level=logging.INFO)
logger = logging.getLogger(__name__)

def json_serial(obj):
    """JSON serializer for objects not serializable by default json code"""

    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError ("Type %s not serializable" % type(obj))

class CloudFlare():
    def __init__(self):
        self.email = config('CLOUD_FLARE_EMAIL')
        self.token = config('CLOUD_FLARE_TOKEN')
        self.domain = config('DOMAIN')
        self.domain_target = config('DOMAIN_TARGET')
        self.headers = { "Authorization": f'Bearer {self.token}'}
    
    def get_dns_records(self):
        id_domain = self.get_id_zone()

        results = requests.get(f'https://api.cloudflare.com/client/v4/zones/{id_domain}/dns_records?name={self.domain_target}',
                            headers=self.headers)
        return results

    def get_id_zone(self):
        get_zone = requests.get(f'https://api.cloudflare.com/client/v4/zones?name={self.domain}',
                    headers=self.headers)
        r_get_zone = get_zone.json()
        id_domain = r_get_zone['result'][0]['id']
        return id_domain

    def change_ip(self, ip):
        id_domain = self.get_id_zone()
        obj_dns_record = self.get_dns_records().json()        
        id_domain_record = obj_dns_record['result'][0]['id']
        url = f'https://api.cloudflare.com/client/v4/zones/{id_domain}/dns_records/{id_domain_record}'
        data = {
            "type": "A",
            "content": ip
        }
        data = json.dumps(data)
        result = requests.patch(url,data=data, headers = self.headers)
        return result

class Conection():
    def __init__(self):
        self.key = config('ACCESS_KEY')
        self.password = config('ACCESS_SECRET')
        self.name_instance = config('INSTANCE_TAG')

    def connection(self):
        client = boto3.client('ec2',
            aws_access_key_id=self.key,
            aws_secret_access_key=self.password,
            region_name = config('REGION_NAME')
            )
        return client

    def get_data(self):
        client = self.connection()            
        try:
            response = client.describe_instances(
                Filters=[
                    {
                        'Name': 'tag:Name',
                        'Values': [
                            self.name_instance,
                        ]
                    },
                ],
                # InstanceIds=[
                #     'string',
                # ],
                #DryRun=True,
                MaxResults=123,
                #NextToken='string'
                )
        except botocore.exceptions.ClientError as ex:
            logger.info(ex)
            return 'error'
        else:
            if len(response['Reservations']) == 0:
                logger.info('Não obteve resultados de consulta da amazon, verifique o nome da instancia e as configurações de login.')
                return 'error'
            if response['Reservations'][0]['Instances'][0]['State']['Name'] == 'stopped':
                logger.info('Instancia está parada. Não possui IP publico.Verifique...')
                return 'error'
            return response

if __name__ == '__main__':
    logger.info('-'*90)
    logger.info('Serviço iniciado.')
    a = Conection()
    result = a.get_data()
    if result != 'error':
        private_ip = result['Reservations'][0]['Instances'][0]['PrivateIpAddress']
        public_ip = result['Reservations'][0]['Instances'][0]['PublicIpAddress']
        logger.info(f'Informações capturadas da instancia: Private IP:{private_ip} | Public IP: {public_ip}')

        logger.info(f'Checando DNS records...')
        cloud = CloudFlare()
        dns_records = cloud.get_dns_records()
        r_dns_records = dns_records.json()
        type_dns = r_dns_records['result'][0]['type']
        ip_dns = r_dns_records['result'][0]['content']

        if ip_dns == public_ip:
            logger.info("IP publico da instancia é igual ao setado no DNS.")
        else:
            logger.info("Ips divergem... iniciando alteração")   
            r_change_ip = cloud.change_ip(public_ip).json()
            if r_change_ip['success'] == True:
                print('DNS alterado com sucesso!')
            else:
                print(r_change_ip['errors'])
    