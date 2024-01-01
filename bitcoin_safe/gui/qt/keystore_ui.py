import logging

from .open_tx_dialog import DescriptorDialog


logger = logging.getLogger(__name__)

from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *
from PySide2.QtSvg import QSvgWidget
from .util import (
    Message,
    add_to_buttonbox,
    icon_path,
    center_in_widget,
    qresize,
    add_tab_to_tabs,
    read_QIcon,
    create_button,
)

from ...keystore import KeyStoreTypes, KeyStoreType, KeyStore
from ...signals import Signals, Signal
from ...util import compare_dictionaries, tx_of_psbt_to_hex
from typing import Callable, List
from .keystore_ui_tabs import KeyStoreUITypeChooser
from .block_change_signals import BlockChangesSignals
import bdkpython as bdk
from ...signer import AbstractSigner

from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *
from .util import (
    icon_path,
    center_in_widget,
    qresize,
    add_tab_to_tabs,
    read_QIcon,
    create_button,
)
from ...keystore import KeyStoreTypes, KeyStoreType, KeyStore
from typing import List
from .block_change_signals import BlockChangesSignals
import bdkpython as bdk
from ...signer import AbstractSigner
from .util import MnemonicLineEdit, CameraInputLineEdit, CameraInputTextEdit
from bitcoin_qrreader import bitcoin_qr
from bitcoin_usb.address_types import DescriptorInfo, AddressType
from bitcoin_usb.software_signer import SoftwareSigner
from bitcoin_usb.gui import USBGui


def icon_for_label(label):
    return (
        read_QIcon("key-gray.png")
        if label.startswith("Recovery")
        else read_QIcon("key.png")
    )


class KeyStoreUI(QObject):
    signal_xpub_changed = Signal()
    signal_seed_changed = Signal()
    signal_fingerprint_changed = Signal()
    signal_key_origin_changed = Signal()

    def __init__(
        self,
        keystore: KeyStore,
        tabs: QTabWidget,
        network: bdk.Network,
        get_address_type: Callable,
    ) -> None:
        super().__init__()

        self.tabs = tabs
        self.keystore = keystore
        self.network = network
        self.get_address_type = get_address_type

        self.tab = self.create()
        self.block_change_signals = BlockChangesSignals(
            [
                self.edit_key_origin,
                self.edit_fingerprint,
                self.edit_label,
                self.edit_xpub,
                self.textEdit_description,
                self.edit_seed,
            ]
        )

        add_tab_to_tabs(
            self.tabs,
            self.tab,
            icon_for_label(keystore.label),
            keystore.label,
            keystore.label,
            focus=True,
        )

    def remove_tab(self):
        self.tabs.removeTab(self.tabs.indexOf(self.tab))

    def set_keystore_from_ui_values(self, keystore: KeyStore):
        logger.debug(f"set_keystore_from_ui_values in {self.keystore.label}")
        ui_keystore = self.get_ui_values_as_keystore()
        if not keystore:
            keystore = self.keystore
        keystore.from_other_keystore(ui_keystore)

    def seed_visibility(self, visible=False):

        self.edit_seed.setHidden(not visible)
        self.label_seed.setHidden(not visible)

        # self.edit_xpub.setHidden(visible)
        # self.edit_fingerprint.setHidden(visible)
        # self.label_xpub.setHidden(visible)
        # self.label_fingerprint.setHidden(visible)

    def on_label_change(self):
        self.tabs.setTabText(self.tabs.indexOf(self.tab), self.edit_label.text())

    def format_key_origin(self):
        standardized = self.edit_key_origin.text().replace("'", "h")
        if standardized != self.edit_key_origin.text():
            # setText will call format_key_origin again
            self.edit_key_origin.setText(standardized)
            return

        address_type: AddressType = self.get_address_type()
        expected = address_type.key_origin(self.network)
        if expected != self.edit_key_origin.text():
            self.edit_key_origin.setStyleSheet("QLineEdit { background-color: red; }")
            self.edit_key_origin.setToolTip(
                f"Standart for the selected address type {address_type.name} is {expected}.  Please correct if you are not sure."
            )
            self.edit_xpub.setStyleSheet("QTextEdit { background-color: red; }")
            self.edit_xpub.setToolTip(
                f"The xPub origin {self.edit_key_origin.text()} and the xPub belong together. Please choose the correct xPub origin pair."
            )
        else:
            self.edit_key_origin.setStyleSheet("")  # Resetting to default style
            self.edit_xpub.setStyleSheet("")
            self.edit_key_origin.setToolTip(f"")
            self.edit_xpub.setToolTip(f"")
        self.edit_key_origin.setPlaceholderText(expected)

    def on_key_origin_change(self, text):
        self.format_key_origin()
        self.signal_key_origin_changed.emit()

    def _on_handle_input(self, data: bitcoin_qr.Data, parent: QWidget = None):
        if data.data_type == bitcoin_qr.DataType.KeyStoreInfo:
            # {
            #         "fingerprint": groups[0],
            #         "key_origin": "m/" + groups[1].replace("h", "'"),
            #         "xpub": groups[2],
            #         "further_derivation_path": groups[3],
            #     }
            if data.data.get("xpub"):
                self.edit_xpub.setText(data.data.get("xpub"))
            if data.data.get("key_origin"):
                self.edit_key_origin.setText(data.data.get("key_origin"))
            if data.data.get("fingerprint"):
                self.edit_fingerprint.setText(data.data.get("fingerprint"))
        elif data.data_type == bitcoin_qr.DataType.Xpub:
            self.edit_xpub.setText(data.data)
        elif data.data_type == bitcoin_qr.DataType.Fingerprint:
            self.edit_fingerprint.setText(data.data)
        elif data.data_type in [
            bitcoin_qr.DataType.Descriptor,
            bitcoin_qr.DataType.MultiPathDescriptor,
        ]:
            Message(
                "Please paste descriptors into the descriptor field in the top right."
            ).show_message()
        elif isinstance(data.data, str) and parent:
            parent.setText(data.data)
        else:
            Exception("Could not recognize the QR Code")

    def create(self):
        tab = QWidget()
        self.tabs.setTabText(
            self.tabs.indexOf(tab),
            QCoreApplication.translate("tab", "Signer settings", None),
        )

        self.horizontalLayout_6 = QHBoxLayout(tab)
        self.horizontalLayout_6.setContentsMargins(
            0, 0, 0, 0
        )  # Left, Top, Right, Bottom margins

        self.box_left = QWidget(tab)
        self.box_left_layout = QVBoxLayout(self.box_left)
        self.box_left_layout.setContentsMargins(
            0, 0, 0, 0
        )  # Left, Top, Right, Bottom margins
        self.box_left_layout.setSpacing(0)
        self.box_form = QWidget(self.box_left)
        self.box_left_layout.addWidget(self.box_form)

        label_keystore_label = QLabel(self.box_form)
        self.edit_label = QLineEdit(self.box_form)
        label_keystore_label.setHidden(True)
        self.edit_label.setHidden(True)
        self.label_fingerprint = QLabel(self.box_form)
        self.edit_fingerprint = CameraInputLineEdit(
            custom_handle_input=self._on_handle_input
        )
        label_key_origin = QLabel(self.box_form)
        self.edit_key_origin = CameraInputLineEdit(
            custom_handle_input=self._on_handle_input
        )
        self.label_xpub = QLabel(self.box_form)
        self.edit_xpub = CameraInputTextEdit(custom_handle_input=self._on_handle_input)
        self.edit_xpub.setMinimumHeight(30)
        self.edit_xpub.setMinimumWidth(400)
        self.label_seed = QLabel()
        self.edit_seed = MnemonicLineEdit()

        # put them on the formLayout
        self.formLayout = QFormLayout(self.box_form)
        self.formLayout.setWidget(1, QFormLayout.LabelRole, label_keystore_label)
        self.formLayout.setWidget(1, QFormLayout.FieldRole, self.edit_label)
        self.formLayout.setWidget(2, QFormLayout.LabelRole, self.label_fingerprint)
        self.formLayout.setWidget(2, QFormLayout.FieldRole, self.edit_fingerprint)
        self.formLayout.setWidget(3, QFormLayout.LabelRole, label_key_origin)
        self.formLayout.setWidget(3, QFormLayout.FieldRole, self.edit_key_origin)
        self.formLayout.setWidget(4, QFormLayout.LabelRole, self.label_xpub)
        self.formLayout.setWidget(4, QFormLayout.FieldRole, self.edit_xpub)
        self.formLayout.setWidget(5, QFormLayout.LabelRole, self.label_seed)
        self.formLayout.setWidget(5, QFormLayout.FieldRole, self.edit_seed)
        self.seed_visibility(self.network in KeyStoreTypes.seed.networks)

        # add the buttons
        self.button_chooser = KeyStoreUITypeChooser(self.network)
        self.button_chooser.button_qr.clicked.connect(
            lambda: self.edit_fingerprint.camera_button.click()
        )
        self.button_chooser.button_hwi.clicked.connect(lambda: self.on_hwi_click())

        def process_input(s: str):
            res = bitcoin_qr.Data.from_str(s, self.network)
            self._on_handle_input(res)

        self.button_chooser.button_file.clicked.connect(
            lambda: DescriptorDialog(self.network, on_open=process_input).show()
        )
        self.box_left_layout.addWidget(self.button_chooser.widget)

        self.horizontalLayout_6.addWidget(self.box_left)

        self.widget_8 = QWidget(tab)
        self.verticalLayout_3 = QVBoxLayout(self.widget_8)
        self.widget_6 = QWidget(self.widget_8)
        self.verticalLayout_5 = QVBoxLayout(self.widget_6)
        self.label_4 = QLabel(self.widget_6)

        self.verticalLayout_5.addWidget(self.label_4)

        self.textEdit_description = QTextEdit(self.widget_6)
        self.verticalLayout_5.addWidget(self.textEdit_description)

        self.verticalLayout_3.addWidget(self.widget_6)

        self.horizontalLayout_6.addWidget(self.widget_8)

        label_keystore_label.setText(QCoreApplication.translate("tab", "Label", None))
        self.label_fingerprint.setText(
            QCoreApplication.translate("tab", "Fingerprint", None)
        )
        label_key_origin.setText(QCoreApplication.translate("tab", "xPub Origin", None))
        self.label_xpub.setText(QCoreApplication.translate("tab", "xPub", None))
        self.label_seed.setText(QCoreApplication.translate("tab", "Seed", None))
        self.label_4.setText(QCoreApplication.translate("tab", "Description", None))
        self.textEdit_description.setPlaceholderText(
            QCoreApplication.translate("tab", "Useful information about signer", None)
        )

        self.edit_xpub.textChanged.connect(self.signal_xpub_changed)
        self.edit_seed.textChanged.connect(self.signal_seed_changed)
        self.edit_fingerprint.textChanged.connect(self.on_edit_fingerprint)
        self.edit_key_origin.textChanged.connect(self.on_key_origin_change)
        self.edit_label.textChanged.connect(self.on_label_change)
        return tab

    def on_hwi_click(self):
        address_type = self.get_address_type()
        usb = USBGui(self.network)
        key_origin = address_type.key_origin(self.network)
        fingerprint, xpub = usb.get_fingerprint_and_xpub(key_origin=key_origin)
        self.edit_xpub.setText(xpub)
        self.edit_fingerprint.setText(fingerprint)
        self.edit_key_origin.setText(key_origin)

    def set_formatting(self):
        # disable this for now.
        return
        if self.edit_fingerprint.isEnabled() and len(self.edit_fingerprint.text()) != 8:
            self.edit_fingerprint.setStyleSheet(
                "QLineEdit { background-color: #ff6c54; }"
            )
        else:
            self.edit_fingerprint.setStyleSheet(
                "QLineEdit { background-color: white; }"
            )

    def on_edit_fingerprint(self, new_value):
        self.set_formatting()
        self.signal_fingerprint_changed.emit()

    def get_ui_values_as_keystore(self) -> KeyStore:
        seed_str = self.edit_seed.text().strip()

        if seed_str:
            mnemonic = bdk.Mnemonic.from_string(seed_str).as_string()
            software_signer = SoftwareSigner(mnemonic, self.network)
            xpub = software_signer.get_xpubs().get(self.get_address_type())
            fingerprint = software_signer.get_fingerprint()
        else:
            mnemonic = None
            fingerprint = (
                self.edit_fingerprint.text()
                if len(self.edit_fingerprint.text()) == 8
                else None
            )
            xpub = self.edit_xpub.text()

        return KeyStore(
            xpub=xpub,
            fingerprint=fingerprint,
            key_origin=self.edit_key_origin.text(),
            label=self.edit_label.text(),
            mnemonic=mnemonic if mnemonic else None,
            description=self.textEdit_description.toPlainText(),
        )

    def set_ui_from_keystore(self, keystore: KeyStore):
        index = self.tabs.indexOf(self.tab)
        if index >= 0:
            self.tabs.setTabText(index, keystore.label)
            self.tabs.setTabIcon(index, icon_for_label(keystore.label))

        with self.block_change_signals:
            self.edit_xpub.setText(keystore.xpub if keystore.xpub else "")
            self.edit_fingerprint.setText(
                keystore.fingerprint if keystore.fingerprint else ""
            )
            self.edit_key_origin.setText(
                keystore.key_origin if keystore.key_origin else ""
            )
            self.edit_label.setText(keystore.label)
            self.textEdit_description.setPlainText(keystore.description)

            self.set_formatting()

            if keystore.mnemonic:
                self.edit_seed.setText(keystore.mnemonic)


class SignedUI(QObject):
    def __init__(
        self,
        text: str,
        psbt: bdk.PartiallySignedTransaction,
        tabs: QTabWidget,
        network: bdk.Network,
        key_label: str,
    ) -> None:
        super().__init__()
        self.text = text
        self.psbt = psbt
        self.tabs = tabs
        self.network = network
        self.key_label = key_label

        self.ui_signer_tab = self.create()

        add_tab_to_tabs(
            self.tabs,
            self.ui_signer_tab,
            read_QIcon("confirmed.png"),
            key_label,
            f"Signed with {key_label}",
            focus=True,
        )

    def create(self):
        tab = QWidget()
        self.layout_keystore_buttons = QHBoxLayout(tab)

        self.edit_signature = QTextEdit()
        self.edit_signature.setMinimumHeight(30)
        self.edit_signature.setReadOnly(True)
        self.edit_signature.setText(str(self.text))
        self.layout_keystore_buttons.addWidget(self.edit_signature)

        return tab

    def remove_tab(self):
        self.tabs.removeTab(self.tabs.indexOf(self.ui_signer_tab))


class SignerUI(QObject):
    signal_signature_added = Signal(bdk.PartiallySignedTransaction)

    def __init__(
        self,
        signers: List[AbstractSigner],
        psbt: bdk.PartiallySignedTransaction,
        tabs: QTabWidget,
        network: bdk.Network,
        key_label: str,
        wallet_id: str,
    ) -> None:
        super().__init__()
        self.signers = signers
        self.psbt = psbt
        self.tabs = tabs
        self.network = network
        self.key_label = key_label
        self.wallet_id = wallet_id

        self.ui_signer_tab = self.create()

        add_tab_to_tabs(
            self.tabs,
            self.ui_signer_tab,
            icon_for_label(key_label),
            key_label,
            f"{key_label} contained in wallet {wallet_id}",
            focus=True,
        )

    def create(self):
        tab = QWidget()

        self.layout_keystore_buttons = QVBoxLayout(tab)

        for signer in self.signers:

            def callback_generator(signer):
                def f():
                    signer.sign(self.psbt)

                return f

            button = QPushButton(signer.label)
            button.setMinimumHeight(30)
            button.setIcon(QIcon(icon_path(signer.keystore_type.icon_filename)))
            button.clicked.connect(callback_generator(signer))
            self.layout_keystore_buttons.addWidget(button)

            # forward the signal_signature_added from each signer to self.signal_signature_added
            signer.signal_signature_added.connect(self.signal_signature_added.emit)

        return tab

    def remove_tab(self):
        self.tabs.removeTab(self.tabs.indexOf(self.ui_signer_tab))
