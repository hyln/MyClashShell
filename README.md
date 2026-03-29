# MCS

基于clash core构建，能够帮你自动配置命令行版本的clash并提供简单的使用方法，无需图形化界面支持，方便一些没有图形化界面的嵌入式设备使用。

[动机说明](./doc/motivation.md) · [Quickstart](./doc/quick_start.md) · [局域网共享](./doc/lan_share.md)

```                            
                    SS                   88        
                    8@88                8          
                   :8@ %8                  8      
                   S88   S   88888         8                
                   8X     8                     
                  :8S                       8   
                  8S8   8@                                  
                  8S8  88@8           8      8  
                  8%                         8      
                 %@@          8888           8      
                 S8@                                        
                 8X8                          @             
          X88   :;8S  
        X88     XXX8  SS%   SS% 8X8%888S @@X    X8%
       %S8      8@88  SS%   SS% 88S      @88    8%@
       888      8@88  SSS888SSS 8SX8@8%; @8S    SS8
        8@S    @8S8   SX%   SX% 8SX      @88    S88
         @@8@X8SS8    SS8   SS8 88S8@@88 XS88@8 88888@ 
           8XS8t8
```                            
     
## 常用命令

```
myclash #查看当前myclcash状态
myclash service update_subcribe # 更新订阅
myclash change_subscribe <订阅名>  # 手动切换订阅(不下载新文件)

myclash shell on 
myclash shell off

myclash window off
myclash window on

myclash tui [代理组名] # 在终端打开节点面板（`python -m scripts.tui`；兼容 `python -m tui`）
# 可选：export MYCLASH_TUI_THEME=tokyo-night 切换 TUI 配色（内置主题名见 Textual 文档）
# TUI 字号/字体由终端模拟器决定；等宽推荐 JetBrains Mono、Cascadia Code；中英文混排可用 Sarasa Gothic / Maple Mono

```
