#### Run service

1. Install [requirements](requirements.txt)
2. Change [configuration file](config/tatlin-black-service.ini) according to your needs.
3. Go to project root directory and run:
```
python3 tatlin-black-service.py --daemon --config=./config/tatlin-black-service.ini
```
You can check status with curl:

```
curl http://localhost:4040/status/
```
response should be according to [this handler](./tatlin-black-service.py#L166)


#### Usage
Please check usage example [here](tests/usage_example.py)