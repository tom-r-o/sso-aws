import os.path
import pickle
import webbrowser

from boto3.session import Session
from time import sleep


def get_aws_session(region: str, role_name: str, account_id: str, sso_endpoint: str):
    session = None
    success = False
    filename = 'session.pickle'
    if os.path.exists(filename):
        with open(filename, 'rb') as f:
            creds = pickle.load(f)
            if creds is not None:
                try:
                    session = __create_session(creds, region)
                    __list_s3_buckets(session)
                    success = True
                except Exception as e:
                    pass

    if not success:
        creds = __get_role_creds(role_name, region, account_id, sso_endpoint)
        with open(filename, 'wb') as f:
            pickle.dump(creds, f)
        session = __create_session(creds, region)

    return session


def __create_session(role_creds, region: str):
    session = Session(
        region_name=region,
        aws_access_key_id=role_creds['roleCredentials']['accessKeyId'],
        aws_secret_access_key=role_creds['roleCredentials']['secretAccessKey'],
        aws_session_token=role_creds['roleCredentials']['sessionToken'],
    )
    return session


def __get_role_creds(role_name: str, region: str, account_id: str, sso_endpoint: str):
    session = Session(region_name=region)

    sso_oidc = session.client('sso-oidc')
    client_creds = sso_oidc.register_client(
        clientName='myapp',
        clientType='public',
    )
    device_authorization = sso_oidc.start_device_authorization(
        clientId=client_creds['clientId'],
        clientSecret=client_creds['clientSecret'],
        startUrl=sso_endpoint,
    )
    url = device_authorization['verificationUriComplete']
    device_code = device_authorization['deviceCode']
    expires_in = device_authorization['expiresIn']
    interval = device_authorization['interval']
    webbrowser.open(url, autoraise=True)

    token = None
    for n in range(1, expires_in // interval + 1):
        sleep(interval)
        try:
            token = sso_oidc.create_token(
                grantType='urn:ietf:params:oauth:grant-type:device_code',
                deviceCode=device_code,
                clientId=client_creds['clientId'],
                clientSecret=client_creds['clientSecret'],
            )
            break
        except sso_oidc.exceptions.AuthorizationPendingException:
            pass

    if token is None:
        raise Exception("Failed to fetch token")

    access_token = token['accessToken']
    sso = session.client('sso')
    account_roles = sso.list_account_roles(
        accessToken=access_token,
        accountId=account_id,
    )
    roles = account_roles['roleList']
    role = next((obj for obj in roles if obj['roleName'] == role_name), None)
    role_creds = sso.get_role_credentials(
        roleName=role['roleName'],
        accountId=account_id,
        accessToken=access_token,
    )

    return role_creds


def __list_s3_buckets(session, print_buckets=False):
    s3 = session.client('s3')
    response = s3.list_buckets()
    buckets = [bucket['Name'] for bucket in response['Buckets']]
    if print_buckets:
        for bucket in buckets:
            print(bucket)
