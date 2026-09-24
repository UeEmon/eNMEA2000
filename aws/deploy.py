"""Initial deployment only. Uses the user's standard AWS credential chain."""
import argparse
import base64
import ipaddress
import json
from pathlib import Path
import subprocess
from datetime import datetime, timezone
import boto3
from botocore.exceptions import ClientError
p=argparse.ArgumentParser()
for name in ['region','vpc','subnet-a','subnet-b','certificate','web-cidr','udp-cidr','tcp-cidr']:
    p.add_argument('--'+name,required=True)
p.add_argument('--stack',default='nmea-observatory')
p.add_argument('--execute',action='store_true',help='Actually create AWS resources and publish the image')
a=p.parse_args()
for cidr in [a.web_cidr,a.udp_cidr,a.tcp_cidr]: ipaddress.IPv4Network(cidr)
if a.subnet_a==a.subnet_b: p.error('Use two subnets in different Availability Zones')
root=Path(__file__).resolve().parents[1]
print('Plan: build linux/amd64 image, publish ECR, create EC2 + PostgreSQL + ALB + EIP + secrets.')
print('This is a single-node initial deployment. Existing stacks are never overwritten.')
if not a.execute:
    print('No changes made. Add --execute to deploy.');raise SystemExit(0)
subprocess.run(['docker','info'],check=True,stdout=subprocess.DEVNULL)
s=boto3.Session(region_name=a.region)
account=s.client('sts').get_caller_identity()['Account']
cf=s.client('cloudformation')
try:
    cf.describe_stacks(StackName=a.stack)
except ClientError as e:
    if e.response['Error']['Code']!='ValidationError' or 'does not exist' not in e.response['Error']['Message']: raise
else: raise SystemExit('Stack already exists. Update intentionally using the documented procedure.')
subnets=s.client('ec2').describe_subnets(SubnetIds=[a.subnet_a,a.subnet_b])['Subnets']
if any(x['VpcId']!=a.vpc for x in subnets) or len({x['AvailabilityZone'] for x in subnets})!=2:
    raise SystemExit('Subnets must be in this VPC and in two different Availability Zones.')
template=(root/'aws/cloudformation.json').read_text()
cf.validate_template(TemplateBody=template)
ecr=s.client('ecr')
try: ecr.describe_repositories(repositoryNames=['nmea-observatory'])
except ecr.exceptions.RepositoryNotFoundException:
    ecr.create_repository(repositoryName='nmea-observatory',imageScanningConfiguration={'scanOnPush':True},imageTagMutability='IMMUTABLE')
auth=ecr.get_authorization_token()['authorizationData'][0]
username,password=base64.b64decode(auth['authorizationToken']).decode().split(':',1)
registry=f'{account}.dkr.ecr.{a.region}.amazonaws.com'
subprocess.run(['docker','login','--username',username,'--password-stdin',registry],input=password,text=True,check=True)
tag=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
image=f'{registry}/nmea-observatory:{tag}'
subprocess.run(['docker','buildx','build','--platform','linux/amd64','--load','-t',image,str(root)],check=True)
subprocess.run(['docker','push',image],check=True)
params={'VpcId':a.vpc,'SubnetA':a.subnet_a,'SubnetB':a.subnet_b,'CertificateArn':a.certificate,
        'WebCidr':a.web_cidr,'UdpCidr':a.udp_cidr,'TcpCidr':a.tcp_cidr,'AppImage':image}
response=cf.create_stack(StackName=a.stack,TemplateBody=template,
    Parameters=[{'ParameterKey':k,'ParameterValue':v} for k,v in params.items()],Capabilities=['CAPABILITY_IAM'])
print('Stack creation started:',response['StackId'])
print('Monitor CloudFormation events, then verify the ALB target is healthy. Configure your certificate domain DNS to WebDnsTarget.')
