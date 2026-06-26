import requests
import uuid

base = 'http://127.0.0.1:8000/api'

print('Testing backend on', base)
try:
    r = requests.get('http://127.0.0.1:8000')
    print('root:', r.status_code)
except Exception as e:
    print('root error:', e)

email = f'testuser_{uuid.uuid4().hex[:6]}@example.com'
payload = {
    'name': 'Test User',
    'email': email,
    'password': 'TestPass123!',
    'user_type': 'Patient'
}
print('Register payload:', payload)
try:
    r = requests.post(base + '/auth/register', json=payload, timeout=15)
    print('register status', r.status_code)
    print('register body', r.text)
    if r.status_code != 200:
        raise SystemExit('register failed')
    token = r.json().get('token')
    headers = {'Authorization': f'Bearer {token}'}
    r = requests.get(base + '/auth/me', headers=headers, timeout=15)
    print('auth/me', r.status_code, r.text)
    update_payload = {
        'name': 'Test User Updated',
        'phone': '+123456789',
        'profile_data': {'age': 30, 'gender': 'male', 'blood_type': 'O+'}
    }
    r = requests.put(base + '/profile', json=update_payload, headers=headers, timeout=15)
    print('profile update', r.status_code, r.text)
    r = requests.get(base + '/profile', headers=headers, timeout=15)
    print('profile get', r.status_code, r.text)
    loc = {'latitude': 34.5, 'longitude': 69.2, 'address': 'Test Address'}
    r = requests.post(base + '/location', json=loc, headers=headers, timeout=15)
    print('location update', r.status_code, r.text)
    r = requests.get(base + '/location/me', headers=headers, timeout=15)
    print('location me', r.status_code, r.text)
    # Test login with the same credentials
    login_payload = {'email': email, 'password': 'TestPass123!'}
    r = requests.post(base + '/auth/login', json=login_payload, timeout=15)
    print('login status', r.status_code, r.text)
    if r.status_code == 200:
        login_token = r.json().get('token')
        login_headers = {'Authorization': f'Bearer {login_token}'}
        r = requests.post(base + '/auth/logout', headers=login_headers, timeout=15)
        print('logout status', r.status_code, r.text)
    # Test nearby endpoint with current user
    nearby_params = {'user_type': 'Patient', 'latitude': 34.5, 'longitude': 69.2, 'radius_km': 5.0}
    r = requests.get(base + '/nearby', headers=headers, params=nearby_params, timeout=15)
    print('nearby', r.status_code, r.text)
except Exception as e:
    print('error', e)
