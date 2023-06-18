import logging
logger = logging.getLogger(__name__)

from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *

from .category_list import CategoryList
from .recipients import Recipients, CustomDoubleSpinBox
from .slider import CustomSlider
from ...signals import  Signal
import bdkpython as bdk
from typing import List, Dict
from .utxo_list import UTXOList
from ...tx import TXInfos
from ...signals import Signals
from .barchart import MempoolBarChart
from ...mempool import get_prio_fees, fee_to_color, fee_to_depth, fee_to_blocknumber
from PySide2.QtGui import QPixmap, QImage
from ...qr import create_psbt_qr
from PIL import Image
from PIL.ImageQt import ImageQt
from ...keystore import KeyStore
from .util import read_QIcon
from .keystore_ui import SignerUI
from ...signer import SignerWallet
from ...util import psbt_to_hex, Satoshis
from .block_buttons import MempoolButtons, MempoolProjectedBlock
from ...mempool import MempoolData
from ...pythonbdk_types import Recipient
from PySide2.QtCore import Signal, QObject



def create_button_bar(layout, button_texts) -> List[QPushButton]:
    button_bar = QWidget()
    button_bar_layout = QHBoxLayout(button_bar)

    
    buttons = []
    for button_text in button_texts:
        button = QPushButton(button_bar)
        button.setText(button_text)
        button.setMinimumHeight(30)
        button_bar_layout.addWidget(button)
        buttons.append(button)

    layout.addWidget(button_bar)        
    return buttons


def create_groupbox(layout, title=None):
    g = QGroupBox()
    if title:
        g.setTitle(title)
    g_layout = QVBoxLayout(g)
    layout.addWidget(g)
    return g, g_layout



class QRLabel(QLabel):
    def __init__(self, *args, width=200, clickable=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.setScaledContents(True)  # Enable automatic scaling
        self.pil_image = None     
        self.enlarged_image  = None   

    def enlarge_image(self):
        if not self.enlarged_image:
            return

        if self.enlarged_image.isVisible():
            self.enlarged_image.close()
        else:
            self.enlarged_image.show()

    def mousePressEvent(self, event):
        self.enlarge_image()

    def set_image(self, pil_image):
        self.pil_image = pil_image
        self.enlarged_image = EnlargedImage(self.pil_image)
        qpix = QPixmap.fromImage(ImageQt(self.pil_image))
        self.setPixmap(qpix)


    def resizeEvent(self, event):
        size = min(self.width(), self.height())
        self.resize(size, size)

    def sizeHint(self):
        size = min(super().sizeHint().width(), super().sizeHint().height())
        return QSize(size, size)

    def minimumSizeHint(self):
        size = min(super().minimumSizeHint().width(), super().minimumSizeHint().height())
        return QSize(size, size)        
        

class EnlargedImage(QLabel):
    def __init__(self, image):
        super().__init__()
        self.setScaledContents(True)  # Enable automatic scaling

        self.setWindowFlags(Qt.FramelessWindowHint)
        screen_resolution = QApplication.desktop().screenGeometry()
        screen_fraction = 3/4
        self.width = self.height = min(screen_resolution.width() , screen_resolution.height() ) * screen_fraction
        self.setGeometry((screen_resolution.width() -self.width)/2, (screen_resolution.height() - self.height)/2, self.width, self.height)
    
        self.image = image
        qpix = QPixmap.fromImage(ImageQt(self.image))
        self.setPixmap(qpix)

    def mousePressEvent(self, event):
        self.close()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()

                

class ExportPSBT(QObject):
    signal_export_psbt_to_file = Signal()
    def __init__(self, layout, allow_edit=False) -> None:
        super().__init__()
        self.psbt = None
        self.tabs = QTabWidget()
        self.tabs.setMaximumWidth(300)
        self.signal_export_psbt_to_file.connect(self.export_psbt)        

        # qr
        self.tab_qr = QWidget()
        self.tab_qr_layout = QHBoxLayout(self.tab_qr)
        self.tab_qr_layout.setAlignment(Qt.AlignVCenter)
        self.qr_label = QRLabel()
        self.qr_label.setWordWrap(True)
        self.tab_qr_layout.addWidget(self.qr_label)
        self.tabs.addTab(self.tab_qr, 'QR')
        
        # right side of qr
        self.tab_qr_right_side = QWidget()
        self.tab_qr_right_side_layout = QVBoxLayout(self.tab_qr_right_side)
        self.tab_qr_right_side_layout.setAlignment(Qt.AlignCenter)
        self.tab_qr_layout.addWidget(self.tab_qr_right_side)
        
        self.button_enlarge_qr = QToolButton()
        self.button_enlarge_qr.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.button_enlarge_qr.setText('Enlarge')
        self.button_enlarge_qr.setIcon(read_QIcon("zoom.png"))        
        self.button_enlarge_qr.setIconSize(QSize(30, 30))  # 24x24 pixels      
        self.button_enlarge_qr.clicked.connect(self.qr_label.enlarge_image)
        self.tab_qr_right_side_layout.addWidget(self.button_enlarge_qr)
        
        self.button_save_qr = QToolButton()
        self.button_save_qr.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.button_save_qr.setText('Save as image')
        self.button_save_qr.setIcon(read_QIcon("download.png"))        
        self.button_save_qr.setIconSize(QSize(30, 30))  # 24x24 pixels      
        self.button_save_qr.clicked.connect(self.export_qrcode)
        self.tab_qr_right_side_layout.addWidget(self.button_save_qr)
        
        
        

        # psbt
        self.tab_psbt = QWidget()
        self.tab_psbt_layout = QVBoxLayout(self.tab_psbt)
        self.edit_psbt = QTextEdit()
        if not allow_edit:
            self.edit_psbt.setReadOnly(True)
        self.tab_psbt_layout.addWidget(self.edit_psbt)
        self.tabs.addTab(self.tab_psbt, 'PSBT')

        # json
        self.tab_json = QWidget()
        self.tab_json_layout = QVBoxLayout(self.tab_json)
        self.edit_json = QTextEdit()
        if not allow_edit:
            self.edit_json.setReadOnly(True)
        self.tab_json_layout.addWidget(self.edit_json)
        self.tabs.addTab(self.tab_json, 'JSON')

        # file
        self.tab_file = QWidget()
        self.tab_file_layout = QVBoxLayout(self.tab_file)
        self.tab_file_layout.setAlignment(Qt.AlignHCenter)
        self.button_file = QToolButton()
        self.button_file.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.button_file.setText('Export PSBT file')
        self.button_file.setIcon(read_QIcon("download.png"))        
        self.button_file.setIconSize(QSize(30, 30))  # 24x24 pixels      
        self.button_file.clicked.connect(self.signal_export_psbt_to_file)        
        self.tab_file_layout.addWidget(self.button_file)
        self.tabs.addTab(self.tab_file, 'Export PSBT file')

        layout.addWidget(self.tabs)        
        
        
    def export_qrcode(self):
        filename = self.save_file_dialog(name_filters=["Image (*.png)", "All Files (*.*)"], default_suffix='png')
        if not filename:
            return        
        self.qr_label.pil_image.save(filename)
        
        
    def set_psbt(self, psbt:bdk.PartiallySignedTransaction):
        self.psbt:bdk.PartiallySignedTransaction = psbt
        self.edit_psbt.setText(psbt.serialize())
        json_text = psbt.json_serialize()
        import json
        json_text = json.dumps( json.loads(json_text), indent=4 )
        self.edit_json.setText(json_text)
        
        img = create_psbt_qr(psbt)
        if img:
            self.qr_label.set_image(img)
        else:
            self.qr_label.setText('Data too large.\nNo QR Code could be generated')

        
        
    def export_psbt(self):
        filename = self.save_file_dialog(name_filters=["PSBT Files (*.psbt)", "All Files (*.*)"], default_suffix='psbt')
        if not filename:
            return
        
        with open(filename, 'w') as file:
            file.write(self.psbt.serialize())
    
    
    def save_file_dialog(self, name_filters=None, default_suffix='psbt'):
        options = QFileDialog.Options()
        # options |= QFileDialog.DontUseNativeDialog  # Use Qt-based dialog, not native platform dialog

        file_dialog = QFileDialog()
        file_dialog.setOptions(options)
        file_dialog.setWindowTitle("Save File")
        file_dialog.setAcceptMode(QFileDialog.AcceptSave)
        file_dialog.setDefaultSuffix(default_suffix)
        if name_filters:
            file_dialog.setNameFilters(name_filters)

        if file_dialog.exec_() == QFileDialog.Accepted:
            selected_file = file_dialog.selectedFiles()[0]
            # Do something with the selected file path, e.g., save data to the file
            logger.debug(f"Selected save file: {selected_file}")
            return selected_file


class FeeGroup(QObject):
    signal_set_fee = Signal(float)
    def __init__(self, mempool_data:MempoolData, layout, allow_edit=True, is_viewer=False) -> None:
        super().__init__()
        
        self.allow_edit = allow_edit
        
        # add the groupBox_Fee
        self.groupBox_Fee = QGroupBox()
        self.groupBox_Fee.setTitle("Fee")
        self.groupBox_Fee.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.groupBox_Fee.setAlignment(Qt.AlignTop)
        layout_h_fee = QVBoxLayout(self.groupBox_Fee)                
        layout_h_fee.setAlignment(Qt.AlignHCenter)
        layout_h_fee.setContentsMargins(layout.contentsMargins().left()/5, layout.contentsMargins().top()/5, layout.contentsMargins().right()/5, layout.contentsMargins().bottom()/5)

        if is_viewer:
            self.mempool = MempoolProjectedBlock(mempool_data)
        else:
            self.mempool = MempoolButtons(mempool_data, button_count=3)
            
        if allow_edit:
            self.mempool.signal_click.connect(self.set_fee)        
        layout_h_fee.addWidget(self.mempool.button_group, alignment=Qt.AlignHCenter)
        
        
        
        self.widget_around_spin_box = QWidget()
        self.widget_around_spin_box_layout = QHBoxLayout(self.widget_around_spin_box)
        self.widget_around_spin_box_layout.setContentsMargins(0, 0, 0, 0)  # Remove margins
        layout_h_fee.addWidget(self.widget_around_spin_box, alignment=Qt.AlignHCenter)
                
        self.spin_fee = QDoubleSpinBox()
        if not allow_edit:
            self.spin_fee.setReadOnly(True)
        self.spin_fee.setRange(0.0, 100.0)  # Set the acceptable range
        self.spin_fee.setSingleStep(1)  # Set the step size
        self.spin_fee.setDecimals(1)  # Set the number of decimal places
        self.spin_fee.setMaximumWidth(45)
        self.spin_fee.editingFinished.connect(lambda: self.set_fee(self.spin_fee.value()))
        # self.mempool.mempool_data.signal_current_data_updated.connect(self.update_spin_fee)
                
        self.widget_around_spin_box_layout.addWidget(self.spin_fee)        

        self.spin_label = QLabel()
        self.spin_label.setText("sat/vB")
        self.widget_around_spin_box_layout.addWidget(self.spin_label)  
              
        self.spin_label2 = QLabel()
        layout_h_fee.addWidget(self.spin_label2, alignment=Qt.AlignHCenter)        
            

        layout.addWidget(self.groupBox_Fee)

            
    def set_fee(self, fee):
        self.spin_fee.setValue(fee)
        self.mempool.set_fee(fee)
        
        self.spin_label2.setText(f"in ~{fee_to_blocknumber(self.mempool.mempool_data.data, fee)}. Block")
        self.signal_set_fee.emit(fee)
        
    def update_spin_fee(self):
        self.spin_fee.setRange(1, self.mempool.data[:,0].max())  # Set the acceptable range 
    



class UITX_Base(QObject):
    def __init__(self, signals:Signals, mempool_data:MempoolData) -> None:
        super().__init__()
        self.signals = signals
        self.mempool_data = mempool_data




    def create_recipients(self, layout, parent=None, allow_edit=True):
        recipients =  Recipients(self.signals, allow_edit=allow_edit)        
        layout.addWidget(recipients)
        recipients.setMinimumWidth(250)                            
        return recipients




class UITX_Viewer(UITX_Base):
    signal_edit_tx = Signal()
    signal_save_psbt = Signal()
    signal_broadcast_tx = Signal()
    def __init__(self, psbt:bdk.PartiallySignedTransaction, signals:Signals, network:bdk.Network, mempool_data:MempoolData, fee_rate=None) -> None:
        super().__init__(signals=signals, mempool_data=mempool_data)
        self.psbt:bdk.PartiallySignedTransaction = psbt
        self.network = network
        self.fee_rate = fee_rate

        self.signers:List[SignerWallet] = []

        
        self.main_widget = QWidget()
        self.main_widget_layout = QVBoxLayout(self.main_widget)


        self.upper_widget = QWidget(self.main_widget)
        self.main_widget_layout.addWidget(self.upper_widget)
        self.upper_widget_layout = QHBoxLayout(self.upper_widget)
        
        # in out
        self.tabs_inputs_outputs = QTabWidget(self.main_widget)
        self.upper_widget_layout.addWidget(self.tabs_inputs_outputs)

        #
        self.tab_inputs = QWidget(self.main_widget)
        self.tab_inputs_layout = QVBoxLayout(self.tab_inputs)
        self.tabs_inputs_outputs.addTab(self.tab_inputs, 'Inputs')
        
        self.tab_outputs = QWidget(self.main_widget)
        self.tab_outputs_layout = QVBoxLayout(self.tab_outputs)
        self.tabs_inputs_outputs.addTab(self.tab_outputs, 'Outputs')        
        self.tabs_inputs_outputs.setCurrentWidget(self.tab_outputs)
        
        self.recipients = self.create_recipients(self.tab_outputs_layout, 
                                            allow_edit=False)


        # fee
        self.fee_group = FeeGroup(self.mempool_data, self.upper_widget_layout, allow_edit=False, is_viewer=True)
        
        
        self.lower_widget = QWidget(self.main_widget)
        self.lower_widget.setMaximumHeight(220)
        self.main_widget_layout.addWidget(self.lower_widget)
        self.lower_widget_layout = QHBoxLayout(self.lower_widget)
        
        # signers
        self.tabs_signers = QTabWidget(self.main_widget)
        self.lower_widget_layout.addWidget(self.tabs_signers)

        #
        self.add_all_signer_tabs()
        

        # exports
        self.export_psbt = ExportPSBT(self.lower_widget_layout, allow_edit=False)
        
        

        # buttons
        (self.button_edit_tx,self.button_save_tx,self.button_broadcast_tx,) = create_button_bar(self.main_widget_layout, 
                                                                                                     button_texts=["Edit Transaction",
                                                                                                                   "Save Transaction",
                                                                                                                   "Broadcast Transaction"
                                                                                                                   ])
        self.button_broadcast_tx.setEnabled(False)
        self.button_broadcast_tx.clicked.connect(self.broadcast)
        self.set_psbt(psbt, fee_rate=fee_rate)
        
        
    def broadcast(self):
        logger.debug(f'broadcasting {psbt_to_hex(self.psbt)}')
        tx = self.psbt.extract_tx()
        self.signers[0].wallet.blockchain.broadcast(tx)
        self.signal_broadcast_tx.emit()


    def add_all_signer_tabs(self):
        # collect all wallets
        inputs:List[bdk.TxIn] = self.psbt.extract_tx().input()
        
        wallet_for_inputs = []
        for this_input in inputs:            
            for wallet_id, utxo in self.signals.utxo_of_outpoint.emit(this_input.previous_output).items():
                if utxo:                   
                    wallet = [wallet for wallet in self.signals.get_wallets.emit().values() if wallet.id == wallet_id][0]
                    wallet_for_inputs.append(wallet)
            
        if None in wallet_for_inputs:
            logger.warning(f'Cannot sign for all the inputs {wallet_for_inputs.index(None)} with the currently opened wallets')
        
        logger.debug(f'wallet_for_inputs {[w.id for w in wallet_for_inputs]}')
        
        signers = [] 
        for wallet in set(wallet_for_inputs): # removes all duplicate wallets
            for keystore in wallet.keystores:
                # TODO: once the bdk ffi has Signers (also hardware signers), I cann add here the signers
                # for now only mnemonic signers are supported
                # signers.append(SignerKeyStore(....))
                # signers.append(SignerHWI(....))
                pass
            signers.append(SignerWallet(wallet, self.network))
        self.signers = list(set(signers)) # removes all duplicate keystores

        logger.debug(f'signers {[k.label for k in signers]}')
        self.signeruis = []
        for signer in self.signers: 
            signerui = SignerUI(signer, self.psbt, self.tabs_signers, self.network)              
            signerui.signal_signature_added.connect(lambda psbt: self.signature_added(psbt))
            self.signeruis.append(signerui)
        

    def signature_added(self, psbt_with_signatures:bdk.PartiallySignedTransaction):
        has_all_signatures = True   # TODO: This needs to be actually checked
        self.set_psbt(psbt_with_signatures, fee_rate=None if has_all_signatures else self.fee_rate)
        self.button_broadcast_tx.setEnabled(True)     




    def set_psbt(self, psbt:bdk.PartiallySignedTransaction, fee_rate=None):
        self.psbt:bdk.PartiallySignedTransaction = psbt
        self.export_psbt.set_psbt(psbt)
        
        fee_rate = self.psbt.fee_rate().as_sat_per_vb() if fee_rate is None else fee_rate
        
        self.fee_group.set_fee(fee_rate)            
        
        outputs :List[bdk.TxOut] = psbt.extract_tx().output()
        
        
        
        self.recipients.recipients = [Recipient(
                                    address=bdk.Address.from_script(output.script_pubkey, self.network).as_string(),
                                    amount=output.value
                                        )
                                      for output in outputs]


class UITX_Creator(UITX_Base):
    signal_create_tx = Signal(TXInfos)
    signal_set_category_coin_selection = Signal(TXInfos)
    
    def __init__(self, mempool_data:MempoolData, categories:List[str], utxo_list:UTXOList,  signals:Signals, get_sub_texts, enable_opportunistic_merging_fee_rate=5) -> None:
        super().__init__(signals=signals, mempool_data=mempool_data)
        self.categories = categories
        self.utxo_list = utxo_list
        self.get_sub_texts = get_sub_texts
        self.enable_opportunistic_merging_fee_rate = enable_opportunistic_merging_fee_rate
        
        utxo_list.selectionModel().selectionChanged.connect(self.update_labels)
        
        

        self.main_widget = QWidget()
        self.main_widget_layout = QHBoxLayout(self.main_widget)
        
        self.create_inputs_selector(self.main_widget_layout)
        

        self.widget_right_hand_side = QWidget(self.main_widget)
        
        self.widget_right_hand_side_layout = QVBoxLayout(self.widget_right_hand_side)        
        
        self.widget_right_top = QWidget(self.main_widget)
        self.widget_right_top_layout = QHBoxLayout(self.widget_right_top)        
        
        self.groupBox_outputs, self.groupBox_outputs_layout = create_groupbox(self.widget_right_top_layout)
        self.recipients = self.create_recipients(self.groupBox_outputs_layout)
        self.recipients.signal_clicked_send_max_button.connect(lambda recipient_group_box: self.set_max_amount(recipient_group_box.amount_spin_box))
        self.recipients.add_recipient()                


        self.fee_group = FeeGroup(mempool_data, self.widget_right_top_layout)
        self.fee_group.signal_set_fee.connect(self.on_set_fee)
        
        self.widget_right_hand_side_layout.addWidget(self.widget_right_top)


        (self.button_create_tx,) = create_button_bar(self.widget_right_hand_side_layout, button_texts=["Next Step: Sign Transaction with hardware signers"])
        self.button_create_tx.clicked.connect(lambda: self.signal_create_tx.emit(self.get_ui_tx_infos()))



        self.main_widget_layout.addWidget(self.widget_right_hand_side)


        self.retranslateUi()

        QMetaObject.connectSlotsByName(self.main_widget)

        self.tab_changed(0)
        self.tabs_inputs.currentChanged.connect(self.tab_changed)

    
    def sum_amount_selected_utxos(self) -> Satoshis:
        sum_values = 0
        for index in self.utxo_list.selectionModel().selectedRows():
            # Assuming that the column of interest is column 1
            value = index.sibling(index.row(), self.utxo_list.Columns.SATOSHIS).data()
            if value is not None and value.isdigit():
                sum_values += float(value)
        return Satoshis(sum_values)
    
    def update_labels(self):
        self.uxto_selected_label.setText(f'Currently {self.sum_amount_selected_utxos().str_with_unit()} selected')


    def create_inputs_selector(self, layout):

        self.tabs_inputs = QTabWidget(self.main_widget)
        self.tabs_inputs.setMinimumWidth(200)
        self.tab_inputs_categories = QWidget(self.main_widget)
        self.tabs_inputs.addTab(self.tab_inputs_categories, 'Input Category')
    
        # tab categories        
        self.verticalLayout_inputs = QVBoxLayout(self.tab_inputs_categories)
        self.label_select_input_categories = QLabel('Select a category that fits best to the recipient')
        self.label_select_input_categories.setWordWrap(True)
        self.checkBox_reduce_future_fees = QCheckBox(self.tab_inputs_categories)
        self.checkBox_reduce_future_fees.setChecked(True)


        # Taglist
        self.category_list = CategoryList(self.categories, self.signals, self.get_sub_texts) 
        self.verticalLayout_inputs.addWidget(self.label_select_input_categories)
        self.verticalLayout_inputs.addWidget(self.category_list)

        self.verticalLayout_inputs.addWidget(self.checkBox_reduce_future_fees)


        # tab utxos
        self.tab_inputs_utxos = QWidget(self.main_widget)
        self.verticalLayout_inputs_utxos = QVBoxLayout(self.tab_inputs_utxos)
        self.tabs_inputs.addTab(self.tab_inputs_utxos, 'UTXOs')


        # utxo list
        self.uxto_selected_label = QLabel(self.main_widget)
        self.verticalLayout_inputs_utxos.addWidget(self.uxto_selected_label)
        self.verticalLayout_inputs_utxos.addWidget(self.utxo_list)

        layout.addWidget(self.tabs_inputs)        


    def on_set_fee(self, fee):
        self.checkBox_reduce_future_fees.setChecked(fee<= self.enable_opportunistic_merging_fee_rate)


    def get_ui_tx_infos(self, use_this_tab=None):
        infos = TXInfos()
        infos.opportunistic_merge_utxos = self.checkBox_reduce_future_fees.isChecked()

        for recipient in self.recipients.recipients:
            infos.add_recipient(recipient)        
            
        logger.debug(f'set psbt builder fee {self.fee_group.spin_fee.value()}')
        infos.set_fee_rate(self.fee_group.spin_fee.value())

        if not use_this_tab:
            use_this_tab = self.tabs_inputs.currentWidget()
        
        if use_this_tab == self.tab_inputs_categories:
            infos.categories = self.category_list.get_selected()
        
        if use_this_tab == self.tab_inputs_utxos:
            infos.utxo_strings = [self.utxo_list.item_from_index(idx).text()
                                  for idx in self.utxo_list.selected_in_column(self.utxo_list.Columns.OUTPOINT)]
            
        return infos




    def set_max_amount(self, spin_box:CustomDoubleSpinBox):
        txinfos = self.get_ui_tx_infos()
        utxos_dict = self.signals.signal_get_all_input_utxos.emit(txinfos)
        total_input_value = sum([
            utxo.txout.value
            for wallet_id, utxos in utxos_dict.items()
            for utxo in utxos
            ])
        
        total_output_value = sum([
            recipient.amount
            for recipient in txinfos.recipients            
        ]) # this includes the old value of the spinbox
        
        logger.debug(str((total_input_value, total_output_value, spin_box.value())))
        
        
        max_available_amount = total_input_value - total_output_value  
        spin_box.setValue(spin_box.value()  + max_available_amount   )







    def update_categories(self):
        self.category_list.clear()
        for category in self.categories:
            self.category_list.add(category, sub_text=self.get_sub_texts())
        

    def retranslateUi(self):
        self.main_widget.setWindowTitle(QCoreApplication.translate("self.main_widget", u"self.main_widget", None))   
        self.checkBox_reduce_future_fees.setText(QCoreApplication.translate("self.main_widget", u"Reduce future fees\n"
"by merging small inputs now", None))




    @Slot(int)
    def tab_changed(self, index):
        # Slot called when the current tab changes
        # print(f"Tab changed to index {index}")

        if index == 0:
            self.tabs_inputs.setMaximumWidth(200)
            self.groupBox_outputs.setMaximumWidth(80000)
        elif index == 1:
            self.tabs_inputs.setMaximumWidth(80000)
            self.groupBox_outputs.setMaximumWidth(500)
            
            # take the coin selection from the category to the utxo tab
            self.signal_set_category_coin_selection.emit(self.get_ui_tx_infos(self.tab_inputs_categories))
            
