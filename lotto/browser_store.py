"""구매 기록만 현재 브라우저 저장소에 보관한다. 공개 저장소로 전송하지 않는다."""
import streamlit as st
import streamlit.components.v2 as components

from . import purchases

STORE_JS = """
export default function({data, parentElement, setStateValue}) {
  const label = document.createElement('span');
  label.style.fontSize = '12px'; label.style.color = '#637883';
  parentElement.replaceChildren(label);
  const storageKey = 'lotto-lab-purchases-v1';
  try {
    if (!data.ready) {
      label.textContent = '이 브라우저의 구매 기록을 불러오는 중…';
      if (parentElement.readNonce !== data.nonce) {
        parentElement.readNonce = data.nonce;
        const saved = JSON.parse(localStorage.getItem(storageKey) || '[]');
        setStateValue('restored', {nonce:data.nonce, records:saved});
      }
    } else {
      const previous = JSON.parse(localStorage.getItem(storageKey) || '[]');
      if (!Array.isArray(previous)) throw new Error('잘못된 저장 형식');
      const merged = new Map(previous.map(r => [r.id, r]));
      for (const r of data.records) {
        const old = merged.get(r.id);
        if (!old || r.updated_at >= old.updated_at) merged.set(r.id, r);
      }
      localStorage.setItem(storageKey, JSON.stringify([...merged.values()]));
      label.textContent = '구매 기록을 이 브라우저에 저장했습니다. 공용 기기에서는 사용에 주의하세요.';
    }
  } catch (e) {
    label.textContent = '브라우저 자동 저장을 사용할 수 없습니다. 구매 이력 JSON 백업을 내려받으세요.';
    if (!data.ready && parentElement.failNonce !== data.nonce) {
      parentElement.failNonce = data.nonce;
      setStateValue('restored', {nonce:data.nonce, records:[], error:true});
    }
  }
}
"""

store = components.component("purchase_browser_store", js=STORE_JS)


def sync(db, nonce):
    result = store(key="purchase_browser_store", data={"nonce": nonce, "ready": st.session_state.get("purchase_browser_ready", False), "records": purchases.records(db)}, default={"restored": None}, on_restored_change=lambda: None, height=32)
    payload = result.restored
    if not st.session_state.get("purchase_browser_ready") and payload and payload.get("nonce") == nonce:
        try:
            purchases.import_records(db, payload["records"])
        except (ValueError, TypeError) as exc:
            st.session_state.purchase_browser_error = str(exc)
            return
        st.session_state.purchase_browser_ready = True
        st.rerun()
    if st.session_state.get("purchase_browser_error"):
        st.warning("저장된 구매 기록을 확인하세요: " + st.session_state.purchase_browser_error)
