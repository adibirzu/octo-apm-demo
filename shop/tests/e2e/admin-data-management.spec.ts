/**
 * Admin Data Management
 *
 * These tests are opt-in because they mutate data. Provide ADMIN_E2E_TOKEN
 * with an admin bearer token to enable them.
 */

import { test, expect } from '@playwright/test';
import {
  SHOP_URL,
  apiGet,
  apiPost,
  apiPut,
  assertObject,
} from './helpers';

const ADMIN_E2E_TOKEN = process.env.ADMIN_E2E_TOKEN ?? '';

test.describe('Admin data management', () => {
  test.skip(!ADMIN_E2E_TOKEN, 'Set ADMIN_E2E_TOKEN to run admin mutation tests');

  const authHeaders = { Authorization: `Bearer ${ADMIN_E2E_TOKEN}` };

  test('admin can create and update customer, shop, product, order, and invoice records', async ({ request }) => {
    const unique = Date.now();
    const customerEmail = `admin-mutation-${unique}@example.invalid`;
    const shopName = `Admin Shop ${unique}`;
    const productSku = `ADM-${unique}`;

    const createCustomer = await apiPost(
      request,
      `${SHOP_URL}/api/admin/customers`,
      {
        name: `Admin Mutation ${unique}`,
        email: customerEmail,
        phone: '+1-555-0199',
        company: 'Admin Test Systems',
        industry: 'Testing',
        revenue: 12000,
        notes: 'created by e2e',
      },
      authHeaders,
    );
    expect(createCustomer.status).toBe(200);
    const createdCustomer = assertObject(assertObject(createCustomer.body)['customer']);
    const customerId = createdCustomer['id'];
    expect(customerId).toBeDefined();

    const updateCustomer = await apiPut(
      request,
      `${SHOP_URL}/api/admin/customers/${customerId}`,
      {
        name: `Admin Mutation ${unique}`,
        email: customerEmail,
        phone: '+1-555-0200',
        company: 'Admin Test Systems',
        industry: 'Testing',
        revenue: 18000,
        notes: 'updated by e2e',
      },
      authHeaders,
    );
    expect(updateCustomer.status).toBe(200);

    const createShop = await apiPost(
      request,
      `${SHOP_URL}/api/admin/shops`,
      {
        name: shopName,
        address: '1 Control Center Way',
        coordinates: '45.0000,25.0000',
        contact_email: `shop-${unique}@example.invalid`,
        contact_phone: '+1-555-0300',
        is_active: 1,
      },
      authHeaders,
    );
    expect(createShop.status).toBe(200);
    const createdShop = assertObject(assertObject(createShop.body)['shop']);
    const shopId = createdShop['id'];
    expect(shopId).toBeDefined();

    const updateShop = await apiPut(
      request,
      `${SHOP_URL}/api/admin/shops/${shopId}`,
      {
        name: `${shopName} Updated`,
        address: '99 Flight Operations Blvd',
        coordinates: '46.0000,26.0000',
        contact_email: `shop-${unique}@example.invalid`,
        contact_phone: '+1-555-0301',
        is_active: 1,
      },
      authHeaders,
    );
    expect(updateShop.status).toBe(200);

    const createProduct = await apiPost(
      request,
      `${SHOP_URL}/api/admin/products`,
      {
        name: `Admin Product ${unique}`,
        sku: productSku,
        description: 'created by e2e',
        price: 799.99,
        stock: 12,
        category: 'Admin Test',
        image_url: '/static/img/products/drn_001.jpg',
        is_active: 1,
      },
      authHeaders,
    );
    expect(createProduct.status).toBe(200);
    const createdProduct = assertObject(assertObject(createProduct.body)['product']);
    const productId = createdProduct['id'];
    expect(productId).toBeDefined();

    const updateProduct = await apiPut(
      request,
      `${SHOP_URL}/api/admin/products/${productId}`,
      {
        name: `Admin Product ${unique}`,
        sku: productSku,
        description: 'updated by e2e',
        price: 849.99,
        stock: 9,
        category: 'Admin Test',
        image_url: '/static/img/products/drn_002.jpg',
        is_active: 1,
      },
      authHeaders,
    );
    expect(updateProduct.status).toBe(200);

    const createOrder = await apiPost(
      request,
      `${SHOP_URL}/api/admin/orders`,
      {
        customer_id: customerId,
        total: 499.99,
        status: 'pending',
        payment_method: 'wire',
        payment_status: 'pending',
        shipping_address: '1 Test Flight Lane',
        notes: 'created by e2e',
      },
      authHeaders,
    );
    expect(createOrder.status).toBe(200);
    const createdOrder = assertObject(assertObject(createOrder.body)['order']);
    const orderId = createdOrder['id'];
    expect(orderId).toBeDefined();

    const updateOrder = await apiPut(
      request,
      `${SHOP_URL}/api/admin/orders/${orderId}`,
      {
        customer_id: customerId,
        total: 549.99,
        status: 'processing',
        payment_method: 'wire',
        payment_status: 'paid',
        shipping_address: '1 Test Flight Lane',
        notes: 'updated by e2e',
      },
      authHeaders,
    );
    expect(updateOrder.status).toBe(200);

    const createInvoice = await apiPost(
      request,
      `${SHOP_URL}/api/admin/invoices`,
      {
        customer_id: customerId,
        order_id: orderId,
        status: 'issued',
        due_at: '2030-01-01T10:00:00',
        notes: 'created by e2e',
      },
      authHeaders,
    );
    expect(createInvoice.status).toBe(200);
    const createdInvoice = assertObject(assertObject(createInvoice.body)['invoice']);
    const invoiceId = createdInvoice['id'];
    expect(invoiceId).toBeDefined();

    const updateInvoice = await apiPut(
      request,
      `${SHOP_URL}/api/admin/invoices/${invoiceId}`,
      {
        invoice_number: createdInvoice['invoice_number'],
        customer_id: customerId,
        order_id: orderId,
        amount: 549.99,
        currency: 'USD',
        status: 'paid',
        issued_at: '2030-01-01T09:00:00',
        due_at: '2030-01-01T10:00:00',
        paid_at: '2030-01-01T11:00:00',
        notes: 'updated by e2e',
      },
      authHeaders,
    );
    expect(updateInvoice.status).toBe(200);

    const listInvoices = await apiGet(request, `${SHOP_URL}/api/admin/invoices`, authHeaders);
    expect(listInvoices.status).toBe(200);
    const invoices = (assertObject(listInvoices.body)['invoices'] ?? []) as Array<Record<string, unknown>>;
    expect(invoices.some((invoice) => String(invoice['id']) === String(invoiceId))).toBe(true);

    const listShops = await apiGet(request, `${SHOP_URL}/api/admin/shops`, authHeaders);
    expect(listShops.status).toBe(200);
    const shops = (assertObject(listShops.body)['shops'] ?? []) as Array<Record<string, unknown>>;
    expect(shops.some((shop) => String(shop['id']) === String(shopId))).toBe(true);

    const listProducts = await apiGet(request, `${SHOP_URL}/api/admin/products`, authHeaders);
    expect(listProducts.status).toBe(200);
    const products = (assertObject(listProducts.body)['products'] ?? []) as Array<Record<string, unknown>>;
    expect(products.some((product) => String(product['id']) === String(productId))).toBe(true);
  });
});
