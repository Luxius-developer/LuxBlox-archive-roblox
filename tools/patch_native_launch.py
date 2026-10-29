"""Add a targeted native game handoff to the existing hybrid WebView."""
from pathlib import Path

METHOD='''
.method public loadUrl(Ljava/lang/String;)V
    .locals 1
    invoke-static {p1}, Lcom/luxius/luxblox/LegacyLinks;->localize(Ljava/lang/String;)Ljava/lang/String;
    move-result-object p1
    invoke-static {p0, p1}, Lcom/luxius/luxblox/NativeLaunch;->open(Landroid/webkit/WebView;Ljava/lang/String;)Z
    move-result v0
    if-nez v0, :luxblox_native_done
    invoke-super {p0, p1}, Lcom/roblox/a/d;->loadUrl(Ljava/lang/String;)V
    :luxblox_native_done
    return-void
.end method
'''

def patch(root):
    root=Path(root)
    path=root/'smali/com/roblox/client/hybrid/RBHybridWebView.smali'
    source=path.read_text()
    if '.method public loadUrl(Ljava/lang/String;)V' in source:raise ValueError('Unexpected existing loadUrl override')
    path.write_text(source+METHOD)
    helper=root/'smali/com/luxius/luxblox/NativeLaunch.smali';helper.parent.mkdir(parents=True,exist_ok=True)
    helper.write_text(Path(__file__).with_name('NativeLaunch.smali').read_text())

if __name__=='__main__':
    import sys
    patch(sys.argv[1])
