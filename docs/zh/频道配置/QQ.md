## 绑定QQ机器人

1. [登录 QQ 开放平台](https://q.qq.com/#/apps)
2. 选择机器人, 点击创建机器人，填入必要信息创建完成后，点击机器人进入管理界面
3. 在[沙箱配置](https://q.qq.com/qqbot/#/developer/sandbox)页面
    * 在**消息列表配置** 添加成员，把你的 QQ 号添加到管理员
4. 点击二维码扫码扫码添加机器人为好友
    ![扫码添加机器人](./QQ扫码添加机器人.png)
5. 管理 -> 开发管理，生成 AppID + AppSecret 填入 `~/.nanobot/config.json`
```
"qq": {
  "enabled": true,
  "appId": "<AppID>",
  "secret": "<AppSecret>",
  "allowFrom": ["第一次给QQBot发送信息后台显示的ID"]
},
```

