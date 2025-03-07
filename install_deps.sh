sudo yum -y install epel-release --disableplugin=priorities
sudo yum -y update --disableplugin=priorities
sudo yum install nodejs --skip-broken --disableplugin=priorities -y
sudo yum remove libuv --disableplugin=priorities -y
sudo yum install libuv --disableplugin=priorities -y
sudo yum install nodejs --disableplugin=priorities -y
sudo yum install npm --disableplugin=priorities -y
sudo npm install -g aws-cdk -y
