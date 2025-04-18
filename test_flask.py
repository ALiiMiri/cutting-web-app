from flask import Flask

app = Flask(__name__)


@app.route('/')
def hello():
    print("DEBUG: درخواست به / در test_flask رسید!")  # این مهمه
    return "<h1>Flask داره کار میکنه!</h1>"


if __name__ == '__main__':
    # با پورت پیش فرض 5000 اجرا میکنیم
    app.run(debug=True)
