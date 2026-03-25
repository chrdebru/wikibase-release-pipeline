0) Creating the keys

curl -L https://github.com/FiloSottile/mkcert/releases/latest/download/mkcert-v1.4.4-darwin-arm64 -o /usr/local/bin/mkcert
chmod +x /usr/local/bin/mkcert
mkcert -install

mkcert -cert-file config/certs/cert.pem \
       -key-file  config/certs/key.pem \
       sitys.rise.uliege.be query.sitys.rise.uliege.be

1) Build all components locally

./build/build.sh wikibase
./build/build.sh elasticsearch
./build/build.sh wdqs
./build/build.sh wdqs-frontend
./build/build.sh quickstatements

2) Go into deploy

cd ./deploye

3) Pull other images

docker pull traefik:3
docker pull mariadb:10.11

4) Run docker compose (fresh install)

rm ./config/LocalSettings.php
docker compose down -v
docker compose up -d --pull never
