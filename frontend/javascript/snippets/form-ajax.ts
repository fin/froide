const serializeForm = (form: HTMLFormElement) => {
    const enabled = (<HTMLInputElement[]> Array.from(form.elements)).filter(node => !node.disabled)
    const pairs = enabled.map(node => {
      const encoded = [node.name, node.value].map(encodeURIComponent)
      return encoded.join('=')
    })
    return pairs.join('&')
  }

const confirmForm = (form: HTMLElement) => {
  const confirmMessage = form.dataset.confirm
  if (!confirmMessage) {
    return true
  }
  const confirmed = window.confirm(confirmMessage)
  if (!confirmed) {
    return false
  }
  return true
}

const submitFormsAjax = () => {
  const ajaxForms = document.querySelectorAll('form.ajaxified')
  Array.from(ajaxForms).forEach(form => {
    form.addEventListener('submit', function (e) {
      e.preventDefault()

      if (!confirmForm(<HTMLElement>form)) {
        return false;
      }

      const method = form.getAttribute('method') || 'post'
      const url = form.getAttribute('action') || ''
      const data = serializeForm(<HTMLFormElement> form)

      var request = new XMLHttpRequest();
      request.open(method, url, true);
      request.setRequestHeader('Content-type', 'application/x-www-form-urlencoded');
      request.setRequestHeader('X-Requested-With', 'XMLHttpRequest')
      request.onload = function() {
        const data = request.responseText
        if (data[0] === '/') {
          // starts with URL, redirect
          window.location.href = data
          return
        }
        const parent = form.closest('.ajax-parent')
        if (parent) {
          parent.outerHTML = data;
        }
      }
      request.send(data);

      Array.from(form.querySelectorAll('button, input')).forEach(el => {
        el.setAttribute('disabled', '')
      })
    })
  })
}

submitFormsAjax()

export default {
  serializeForm,
  submitFormsAjax
}