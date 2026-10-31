"""개인 구매·추천·메모를 브라우저 저장소에 보관하고 이전 구매 기록을 이관한다."""
import streamlit as st
import streamlit.components.v2 as components

from . import workspace

STORE_JS = """
export default function({data, parentElement, setStateValue}) {
  const label = document.createElement('span');
  label.style.fontSize = '12px'; label.style.color = '#637883';
  parentElement.replaceChildren(label);
  const storageKey = 'lotto-lab-workspace-v2';
  const empty = () => ({version:2,purchases:[],recommendations:[],notes:[]});
  const read = () => {
    const raw = localStorage.getItem(storageKey);
    if (raw) {
      const value = JSON.parse(raw);
      if (value.version !== 2 || !['purchases','recommendations','notes'].every(k => Array.isArray(value[k]))) throw new Error('잘못된 백업');
      return value;
    }
    const legacy = JSON.parse(localStorage.getItem('lotto-lab-purchases-v1') || '[]');
    if (!Array.isArray(legacy)) throw new Error('잘못된 구매 기록');
    return {...empty(),purchases:legacy};
  };
  try {
    if (!data.ready) {
      label.textContent = '이 브라우저의 연구 작업 공간을 불러오는 중…';
      if (parentElement.readNonce !== data.nonce) {
        parentElement.readNonce = data.nonce;
        setStateValue('restored', {nonce:data.nonce, workspace:read()});
      }
    } else {
      const previous = read();
      const saved = empty();
      for (const kind of ['purchases','recommendations','notes']) {
        const merged = new Map(previous[kind].map(r => [r.id,r]));
        for (const r of data.workspace[kind]) {
          const old = merged.get(r.id);
          if (!old || (r.updated_at || r.created_at) >= (old.updated_at || old.created_at)) merged.set(r.id,r);
        }
        saved[kind] = [...merged.values()];
      }
      localStorage.setItem(storageKey, JSON.stringify(saved));
      label.textContent = '구매·추천·메모를 이 브라우저에 저장했습니다. 공용 기기에서는 사용에 주의하세요.';
    }
  } catch (e) {
    label.textContent = '브라우저 자동 저장을 사용할 수 없습니다. 대시보드에서 전체 JSON 백업을 내려받으세요.';
    if (!data.ready && parentElement.failNonce !== data.nonce) {
      parentElement.failNonce = data.nonce;
      setStateValue('restored', {nonce:data.nonce, workspace:empty(), error:true});
    }
  }
}
"""

store = components.component("purchase_browser_store", js=STORE_JS)


def sync(db, nonce):
    result = store(key="purchase_browser_store", data={"nonce": nonce, "ready": st.session_state.get("purchase_browser_ready", False), "workspace": workspace.export_payload(db)}, default={"restored": None}, on_restored_change=lambda: None, height=32)
    payload = result.restored
    if not st.session_state.get("purchase_browser_ready") and payload and payload.get("nonce") == nonce:
        try:
            workspace.import_payload(db, payload["workspace"])
        except (ValueError, TypeError) as exc:
            st.session_state.purchase_browser_error = str(exc)
            return
        st.session_state.purchase_browser_ready = True
        st.rerun()
    if st.session_state.get("purchase_browser_error"):
        st.warning("저장된 구매 기록을 확인하세요: " + st.session_state.purchase_browser_error)
