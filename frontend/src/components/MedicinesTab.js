import React, { useState, useEffect } from 'react';
import { useLanguage } from '../LanguageContext';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Textarea } from './ui/textarea';
import { Switch } from './ui/switch';
import { Badge } from './ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog';
import { Search, Plus, Pill, Trash2, ShoppingCart, Upload } from 'lucide-react';
import api from '../api';
import { toast } from 'sonner';

const MedicinesTab = ({ user }) => {
  const { t } = useLanguage();
  const [medicines, setMedicines] = useState([]);
  const [search, setSearch] = useState('');
  const [showAddForm, setShowAddForm] = useState(false);
  const [form, setForm] = useState({
    name: '', generic_name: '', category: '', manufacturer: '',
    price: '', stock: '', description: '', requires_prescription: false,
  });
  const [orderDialog, setOrderDialog] = useState(null);
  const [orderQty, setOrderQty] = useState(1);
  const [orderAddress, setOrderAddress] = useState('');
  const [prescriptionFile, setPrescriptionFile] = useState(null);

  const isPharmacy = user?.user_type === 'Pharmacy';
  const isPatient = user?.user_type === 'Patient';

  const loadMedicines = async () => {
    try {
      const params = new URLSearchParams();
      if (search) params.append('search', search);
      if (isPharmacy) params.append('pharmacy_id', user.user_id);
      const res = await api.get(`/medicines?${params.toString()}`);
      setMedicines(res.data.medicines || []);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => { loadMedicines(); }, []);

  const handleSearch = (e) => {
    e.preventDefault();
    loadMedicines();
  };

  const handleAdd = async (e) => {
    e.preventDefault();
    try {
      await api.post('/medicines', {
        ...form,
        price: parseFloat(form.price),
        stock: parseInt(form.stock || 0),
      });
      toast.success(t('medicineAdded'));
      setForm({ name: '', generic_name: '', category: '', manufacturer: '', price: '', stock: '', description: '', requires_prescription: false });
      setShowAddForm(false);
      loadMedicines();
    } catch (e) {
      toast.error(e.response?.data?.detail || t('error'));
    }
  };

  const handleDelete = async (id) => {
    try {
      await api.delete(`/medicines/${id}`);
      toast.success('Deleted');
      loadMedicines();
    } catch (e) {
      toast.error(t('error'));
    }
  };

  const uploadPrescription = async (file) => {
    try {
      const formData = new FormData();
      formData.append('file', file);
      const res = await api.post('/upload?purpose=prescription', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setPrescriptionFile(res.data);
      toast.success(t('uploadSuccess'));
    } catch (e) {
      toast.error(t('error'));
    }
  };

  const placeOrder = async () => {
    if (!orderDialog) return;
    try {
      await api.post('/orders', {
        medicine_id: orderDialog.medicine_id,
        quantity: orderQty,
        delivery_address: orderAddress,
        prescription_file_id: prescriptionFile?.file_id,
      });
      toast.success('Order placed!');
      setOrderDialog(null);
      setOrderQty(1);
      setOrderAddress('');
      setPrescriptionFile(null);
      loadMedicines();
    } catch (e) {
      toast.error(e.response?.data?.detail || t('error'));
    }
  };

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="flex items-center gap-2"><Pill className="w-5 h-5" /> {t('medicines')}</CardTitle>
          {isPharmacy && (
            <Button onClick={() => setShowAddForm(!showAddForm)} data-testid="toggle-add-medicine">
              <Plus className="w-4 h-4 me-1" /> {t('addMedicine')}
            </Button>
          )}
        </CardHeader>
        <CardContent className="space-y-4">
          <form onSubmit={handleSearch} className="flex gap-2">
            <Input
              placeholder={t('searchMedicines')}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              data-testid="medicine-search-input"
            />
            <Button type="submit" data-testid="medicine-search-btn"><Search className="w-4 h-4" /></Button>
          </form>

          {isPharmacy && showAddForm && (
            <form onSubmit={handleAdd} className="border rounded-lg p-4 space-y-3" data-testid="add-medicine-form">
              <div className="grid md:grid-cols-2 gap-3">
                <div>
                  <Label className="text-start block">{t('medicineName')} *</Label>
                  <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required data-testid="medicine-name-input" />
                </div>
                <div>
                  <Label className="text-start block">{t('genericName')}</Label>
                  <Input value={form.generic_name} onChange={(e) => setForm({ ...form, generic_name: e.target.value })} />
                </div>
                <div>
                  <Label className="text-start block">{t('category')}</Label>
                  <Input value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} placeholder="antibiotic, painkiller..." />
                </div>
                <div>
                  <Label className="text-start block">{t('manufacturer')}</Label>
                  <Input value={form.manufacturer} onChange={(e) => setForm({ ...form, manufacturer: e.target.value })} />
                </div>
                <div>
                  <Label className="text-start block">{t('price')} *</Label>
                  <Input type="number" step="0.01" value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })} required data-testid="medicine-price-input" />
                </div>
                <div>
                  <Label className="text-start block">{t('stock')}</Label>
                  <Input type="number" value={form.stock} onChange={(e) => setForm({ ...form, stock: e.target.value })} />
                </div>
              </div>
              <div>
                <Label className="text-start block">{t('description')}</Label>
                <Textarea value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
              </div>
              <div className="flex items-center gap-2">
                <Switch checked={form.requires_prescription} onCheckedChange={(c) => setForm({ ...form, requires_prescription: c })} />
                <Label>{t('requiresPrescription')}</Label>
              </div>
              <Button type="submit" data-testid="save-medicine-btn">{t('save')}</Button>
            </form>
          )}

          {medicines.length === 0 ? (
            <p className="text-muted-foreground text-center py-8">{t('noMedicines')}</p>
          ) : (
            <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-3">
              {medicines.map(med => (
                <Card key={med.medicine_id} data-testid={`medicine-${med.medicine_id}`}>
                  <CardContent className="p-4 text-start space-y-2">
                    <div className="flex items-start justify-between">
                      <div>
                        <h4 className="font-semibold">{med.name}</h4>
                        {med.generic_name && <p className="text-xs text-muted-foreground">{med.generic_name}</p>}
                      </div>
                      <Badge variant={med.stock > 0 ? 'default' : 'destructive'}>
                        {med.stock > 0 ? t('inStock') : t('outOfStock')}
                      </Badge>
                    </div>
                    <p className="text-sm text-muted-foreground">{med.pharmacy_name}</p>
                    <div className="flex items-center justify-between">
                      <span className="font-medium text-primary">${med.price?.toFixed(2)}</span>
                      {med.requires_prescription && <Badge variant="outline">Rx</Badge>}
                    </div>
                    {med.category && <Badge variant="secondary">{med.category}</Badge>}
                    <div className="flex gap-2 pt-2">
                      {isPatient && med.stock > 0 && (
                        <Button size="sm" onClick={() => setOrderDialog(med)} data-testid={`order-${med.medicine_id}`}>
                          <ShoppingCart className="w-4 h-4 me-1" /> {t('orderNow')}
                        </Button>
                      )}
                      {isPharmacy && med.pharmacy_id === user.user_id && (
                        <Button size="sm" variant="ghost" onClick={() => handleDelete(med.medicine_id)} data-testid={`delete-${med.medicine_id}`}>
                          <Trash2 className="w-4 h-4" />
                        </Button>
                      )}
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog open={!!orderDialog} onOpenChange={(o) => !o && setOrderDialog(null)}>
        <DialogContent data-testid="order-dialog">
          <DialogHeader><DialogTitle>{t('placeOrder')}: {orderDialog?.name}</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>{t('quantity')}</Label>
              <Input type="number" min="1" max={orderDialog?.stock} value={orderQty} onChange={(e) => setOrderQty(parseInt(e.target.value) || 1)} data-testid="order-quantity-input" />
              <p className="text-xs text-muted-foreground mt-1">Total: ${((orderDialog?.price || 0) * orderQty).toFixed(2)}</p>
            </div>
            <div>
              <Label>{t('deliveryAddress')}</Label>
              <Textarea value={orderAddress} onChange={(e) => setOrderAddress(e.target.value)} data-testid="order-address-input" />
            </div>
            {orderDialog?.requires_prescription && (
              <div>
                <Label>{t('uploadPrescription')} *</Label>
                <input
                  type="file"
                  accept="image/*,application/pdf"
                  onChange={(e) => e.target.files?.[0] && uploadPrescription(e.target.files[0])}
                  className="text-sm"
                  data-testid="prescription-upload"
                />
                {prescriptionFile && <Badge className="mt-2"><Upload className="w-3 h-3 me-1" /> {prescriptionFile.file_id}</Badge>}
              </div>
            )}
            <Button
              onClick={placeOrder}
              disabled={orderDialog?.requires_prescription && !prescriptionFile}
              className="w-full"
              data-testid="confirm-order-btn"
            >
              {t('placeOrder')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default MedicinesTab;
