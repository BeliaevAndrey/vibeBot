#!/bin/bash

echo "Args: --command_mode - командный режим"
echo "no args - режим по умолчанию"
echo "--------------------------------"

source .venv/bin/activate
export $(grep -v '^#' .env | xargs)

if [ -z "$1" ]; then
    python main.py $1
else
    python main.py
fi
