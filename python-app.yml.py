name: Build Python App

on:
  push:
    branches: [ main ]

jobs:
  build:
    runs-on: ubuntu-latest

    steps:
    - name: Checkout code
      uses: actions/checkout@v3

    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: "3.10"

    - name: Install dependencies
      run: |
        pip install -r requirements.txt
        pip install buildozer cython

    - name: Build APK
      run: |
        buildozer init
        echo "[app]\ntitle = Indian Market Price Advisor\npackage.name = marketadvisor\npackage.domain = org.luckyraj\nsource.dir = .\nsource.main = main.py\nversion = 1.0\nrequirements = python3,requests,kivy\n" > buildozer.spec
        buildozer android debug