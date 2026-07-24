#!/usr/bin/env bash

set -euo pipefail

ssh yopazvn@192.168.68.236 \
  'cd /home/yopazvn/yonex && git pull'
