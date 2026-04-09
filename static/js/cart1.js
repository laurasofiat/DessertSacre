// Actualiza el badge del navbar
function cacheCartCount(count) {
  const badge = document.getElementById('cart-count');
  if (badge) badge.textContent = count;
}

// Muestra mensajes de estado en carrito
function updateCartStatus(message, type = 'success') {
  const status = document.getElementById('cart-status');
  if (!status) return;
  status.innerHTML = `<div class="alert alert-${type} alert-dismissible fade show" role="alert">
    ${message}
    <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
  </div>`;
}

// Agregar producto al carrito vía API
async function addToCartAPI(name, price) {
  try {
    const res = await fetch('/agregar_carrito', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nombre: name, precio: price })
    });
    const data = await res.json();
    if (data.success) {
      cacheCartCount(data.total_items || 0);
      updateCartStatus(`Se agregó "${name}" al carrito.`, 'success');
    } else {
      updateCartStatus(data.error || 'No se pudo agregar el producto.', 'danger');
    }
  } catch {
    updateCartStatus('Error de red al agregar el producto.', 'danger');
  }
}

// Inicializa botones "Agregar al carrito"
function initAddToCartButtons() {
  document.querySelectorAll('.btn-warning.add-to-cart').forEach(button => {
    button.addEventListener('click', async e => {
      e.preventDefault();
      const name = button.dataset.name;
      const price = parseFloat(button.dataset.price);
      if (!name || !price) {
        updateCartStatus('No se pudo leer el nombre o precio del producto.', 'danger');
        return;
      }
      await addToCartAPI(name, price);
    });
  });
}

// Actualiza total en carrito
function updateTotalUI(totalPrice, totalItems) {
  const totalEl = document.getElementById('cart-total');
  if (totalEl) totalEl.textContent = `COP ${totalPrice.toLocaleString('es-CO', { minimumFractionDigits:0, maximumFractionDigits:0 })}`;
  cacheCartCount(totalItems);
}

// Actualiza cantidad de producto
async function updateQuantity(index, qty) {
  const res = await fetch('/api/cart/update', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ index, qty })
  });
  return res.json();
}

// Elimina producto del carrito
async function removeItem(index) {
  const res = await fetch('/api/cart/remove', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ index })
  });
  return res.json();
}

function reindexCart() {
  document.querySelectorAll('#cart-items tr').forEach((row, i) => {
    row.dataset.index = i;

    // actualizar botón eliminar
    const btn = row.querySelector('.remove-item');
    if (btn) btn.dataset.index = i;

    // actualizar input cantidad (por si lo usas luego)
    const input = row.querySelector('.qty-input');
    if (input) input.name = `qty_${i}`;
  });
}

// Inicializa tabla del carrito
function initCartTable() {
  document.querySelectorAll('.qty-input').forEach(input => {
    input.addEventListener('change', async () => {
      const row = input.closest('tr');
      const index = Number(row.dataset.index);
      const qty = parseInt(input.value);
      if (isNaN(index) || isNaN(qty) || qty < 1) return;

      const result = await updateQuantity(index, qty);
      if (result.success) updateTotalUI(result.total_price, result.total_items);
      else updateCartStatus(result.error || 'No fue posible actualizar', 'danger');
    });
  });

  document.querySelectorAll('.remove-item').forEach(btn => {
    btn.addEventListener('click', async () => {
      const index = Number(btn.dataset.index);
      if (isNaN(index)) return;

      const result = await removeItem(index);
      if (result.success) {
        updateTotalUI(result.total_price, result.total_items);
        btn.closest('tr').remove();
        reindexCart(); // 🔥 CLAVE
        updateCartStatus('Producto eliminado', 'success');
      } else updateCartStatus(result.error || 'No fue posible eliminar', 'danger');
    });
  });
}

// Botón checkout
function initCheckoutButton() {
  const checkout = document.getElementById('checkout-btn');
  if (!checkout) return;
  checkout.addEventListener('click', () => window.location.href = '/confirmacion');
}

// Inicialización al cargar la página
window.addEventListener('DOMContentLoaded', () => {
  initAddToCartButtons();
  initCartTable();
  initCheckoutButton();
});
