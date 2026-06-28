关键改动只有两处：
顶部加了一行 import json
add_draft 函数里把 json={"articles": articles} 改成了手动序列化 + data= 发送
