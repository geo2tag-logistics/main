from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User, Group
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.authentication import BasicAuthentication, SessionAuthentication
from rest_framework.response import Response
from rest_framework.views import APIView

from logistics.Geo2TagService import updateDriverPos, deleteFleetChannel, deleteDriverPos, clearAllFleetChannels
from logistics.permissions import is_driver, is_owner, IsOwnerPermission, IsDriverPermission, IsOwnerOrDriverPermission
from .forms import SignUpForm, LoginForm, FleetAddForm, FleetInviteDismissForm, DriverPendingFleetAddDeclineForm, AddTripForm, DriverReportProblemForm, \
    DriverAcceptTripForm, DriverUpdatePosForm
from .models import Fleet, Driver, Owner, DriverStats, Trip
from .serializers import FleetSerializer, DriverSerializer, TripSerializer


class CsrfExemptSessionAuthentication(SessionAuthentication):

    def enforce_csrf(self, request):
        return  # To not perform the csrf check previously happening


class SignUp(APIView):
    def post(self, request):
        form = SignUpForm(request.data)
        if form.is_valid():
            try:
                user = User.objects.create_user(username=form.cleaned_data["login"], email=form.cleaned_data["email"], password=form.cleaned_data["password"])
                if form.cleaned_data["role"] == "1" :
                    user.groups.add(Group.objects.get_or_create(name='OWNER')[0])
                    owner = Owner.objects.create(user=user, first_name=form.cleaned_data["first_name"], last_name=form.cleaned_data["last_name"])
                    user.save()
                    owner.save()
                else:
                    user.groups.add(Group.objects.get_or_create(name='DRIVER')[0])
                    driver = Driver.objects.create(user=user, first_name=form.cleaned_data["first_name"], last_name=form.cleaned_data["last_name"])
                    driver_stats = DriverStats.objects.create(driver=driver)
                    user.save()
                    driver.save()
                    driver_stats.save()
                return Response({"status": "ok"}, status=status.HTTP_201_CREATED)
            except Exception as e:
                return Response({"status": "error", "errors": [str(e)]}, status=status.HTTP_409_CONFLICT)
        else:
            return Response({"status": "error", "errors": ["Invalid post parameters"]}, status=status.HTTP_400_BAD_REQUEST)


class Auth(APIView):
    def post(self, request):
        if not request.user.is_anonymous():
            return Response({"status": "error", "errors": ["Already login"]}, status=status.HTTP_409_CONFLICT)
        form = LoginForm(request.data)
        if form.is_valid():
            try:
                user = authenticate(username=form.cleaned_data["login"], password=form.cleaned_data["password"])
                if user is not None:
                    if user.is_active:
                        login(request, user)
                        return Response({"status": "ok"}, status=status.HTTP_200_OK)
                    else:
                        return Response({"status": "error"}, status=status.HTTP_409_CONFLICT)
            except Exception as e:
                return Response({"status": "error", "errors": [str(e)]}, status=status.HTTP_409_CONFLICT)
        else:
            return Response({"status": "error", "errors": ["Invalid post parameters"]}, status=status.HTTP_400_BAD_REQUEST)


class Logout(APIView):
    def get(self, request):
        if request.user.is_anonymous():
            return Response({"status": "error", "errors": ["Not authorized"]}, status=status.HTTP_409_CONFLICT)
        else:
            logout(request)
            return Response({"status": "ok"}, status=status.HTTP_200_OK)


class FleetList(APIView):
    permission_classes = (IsOwnerOrDriverPermission,)
    authentication_classes = (CsrfExemptSessionAuthentication, BasicAuthentication)

    def get(self, request):
        if is_owner(request.user):
            fleets = Fleet.objects.filter(owner=request.user.owner)
            serialized_fleets = FleetSerializer(fleets, many=True)
            return Response(serialized_fleets.data, status=status.HTTP_200_OK)
        elif is_driver(request.user):
            fleets = request.user.driver.fleets
            serialized_fleets = FleetSerializer(fleets, many=True)
            return Response(serialized_fleets.data, status=status.HTTP_200_OK)
        else:
            return Response({"status": "error", "errors": ["Not authorized"]}, status=status.HTTP_400_BAD_REQUEST)

    def post(self, request):
        current_user = request.user
        print(current_user)
        form = FleetAddForm(request.data)
        owner = request.user.owner
        if form.is_valid():
            try:
                fleet = form.save(commit=False)
                fleet.owner = owner
                fleet.save()
                print(fleet.name, fleet.description, fleet.owner, fleet.id)
                return Response({"status": "ok", "fleet_id": fleet.id}, status=status.HTTP_201_CREATED)
            except:
                return Response({"status": "error"}, status=status.HTTP_409_CONFLICT)
        else:
            return Response({"status": "error"}, status=status.HTTP_400_BAD_REQUEST)


class DriversByFleet(APIView):
    permission_classes = (IsOwnerPermission,)

    def get(self, request, fleet_id):
        if Fleet.objects.get(pk=fleet_id) in Fleet.objects.filter(owner=request.user.owner):
            drivers = Driver.objects.filter(fleets=fleet_id)
            serialized_drivers = DriverSerializer(drivers, many=True)
            return Response(serialized_drivers.data, status=status.HTTP_200_OK)
        else:
            return Response({"status": "error", "errors": ["Wrong fleet_id"]}, status=status.HTTP_409_CONFLICT)


class PendingDriversByFleet(APIView):
    permission_classes = (IsOwnerPermission,)

    def get(self, request, fleet_id):
        if Fleet.objects.get(pk=fleet_id) in Fleet.objects.filter(owner=request.user.owner):
            drivers = Driver.objects.exclude(fleets=fleet_id).exclude(pending_fleets=fleet_id)
            serialized_drivers = DriverSerializer(drivers, many=True)
            return Response(serialized_drivers.data, status=status.HTTP_200_OK)
        else:
            return Response({"status": "error", "errors": ["Wrong fleet_id"]}, status=status.HTTP_409_CONFLICT)


class FleetByIdView(APIView):
    permission_classes = (IsOwnerPermission,)
    authentication_classes = (CsrfExemptSessionAuthentication, BasicAuthentication)

    def get(self, request, fleet_id):
        fleet = Fleet.objects.get(id=fleet_id)
        if fleet in Fleet.objects.filter(owner=request.user.owner):
            serialized_fleet = FleetSerializer(fleet, many=False)
            return Response(serialized_fleet.data, status=status.HTTP_200_OK)
        else:
            return Response({"status": "error"}, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, fleet_id):
        fleet_for_delete = Fleet.objects.get(id=fleet_id)
        if fleet_for_delete in Fleet.objects.filter(owner=request.user.owner):
            deleteFleetChannel()
            fleet_for_delete.delete()
            return Response({"status": "ok"}, status=status.HTTP_200_OK)
        else:
            return Response({"status": "error"}, status=status.HTTP_400_BAD_REQUEST)


# OWNER API
class FleetInvite(APIView):
    permission_classes = (IsOwnerPermission,)
    authentication_classes = (CsrfExemptSessionAuthentication, BasicAuthentication)

    def post(self, request, fleet_id):
        # POST /api/fleet/(?P<fleet_id>[-\w]+)/invite/
        form_offer_invite = FleetInviteDismissForm(request.data)
        if form_offer_invite.is_valid():
            try:
                fleet = Fleet.objects.get(id=fleet_id)
                if fleet in Fleet.objects.filter(owner=request.user.owner):
                    ids = form_offer_invite.cleaned_data.get('driver_id')
                    failed = False
                    ids_fleet_failed = []
                    ids_pending_failed = []
                    for driver_id in ids.split(sep=','):
                        if driver_id != '':
                            driver = Driver.objects.get(id=driver_id)
                            if fleet in driver.fleets.all():
                                ids_fleet_failed.append(driver_id)
                                failed = True
                            elif fleet in driver.pending_fleets.all():
                                ids_pending_failed.append(driver_id)
                                failed = True
                            else:
                                driver.pending_fleets.add(fleet)
                                driver.save()
                    if failed:
                        return Response({"status": "error",
                                         "errors": {"Drivers is already in fleet": ids_fleet_failed,
                                                    "Drivers is already in pending fleet": ids_pending_failed}},
                                        status=status.HTTP_409_CONFLICT)
                    return Response({"status": "ok"}, status=status.HTTP_200_OK)
                else:
                    return Response({"status": "error", "errors": ["Not owner of fleet"]},
                                    status=status.HTTP_409_CONFLICT)
            except Exception as e:
                return Response({"status": "error", "errors": [str(e)]}, status=status.HTTP_409_CONFLICT)
        else:
            return Response({"status": "error"}, status=status.HTTP_400_BAD_REQUEST)


class FleetDismiss(APIView):
    permission_classes = (IsOwnerPermission,)
    authentication_classes = (CsrfExemptSessionAuthentication, BasicAuthentication)

    def post(self, request, fleet_id):
        # POST /api/fleet/(?P<fleet_id>[-\w]+)/dismiss/
        form_dismiss = FleetInviteDismissForm(request.data)
        if form_dismiss.is_valid():
            try:
                fleet = Fleet.objects.get(id=fleet_id)
                if fleet in Fleet.objects.filter(owner=request.user.owner):
                    id = form_dismiss.cleaned_data.get('driver_id')
                    driver = Driver.objects.get(id=id)
                    deleteDriverPos(fleet, driver)
                    driver.fleets.remove(fleet)
                    driver.save()
                    print(fleet.id, id, driver.id)
                    return Response({"status": "ok"}, status=status.HTTP_200_OK)
                else:
                    return Response({"status": "error", "errors": ["Not owner of fleet"]}, status=status.HTTP_409_CONFLICT)
            except:
                return Response({"status": "error"}, status=status.HTTP_409_CONFLICT)
        else:
            return Response({"status": "error"}, status=status.HTTP_400_BAD_REQUEST)


class TripsByFleetUnaccepted(APIView):
    permission_classes = (IsOwnerPermission,)
    authentication_classes = (CsrfExemptSessionAuthentication, BasicAuthentication)

    def get(self, request, fleet_id):
        # GET /api/fleet/(?P<fleet_id>[-\w]+)/trips/unaccepted/
        fleet = get_object_or_404(Fleet, id=fleet_id, owner=request.user.owner)
        trips = Trip.objects.filter(fleet=fleet, driver=None, is_finished=False)
        serialized_trips = TripSerializer(trips, many=True)
        return Response(serialized_trips.data, status=status.HTTP_200_OK)


class TripsByFleetFinished(APIView):
    permission_classes = (IsOwnerPermission,)
    authentication_classes = (CsrfExemptSessionAuthentication, BasicAuthentication)

    def get(self, request, fleet_id):
        # GET /api/fleet/(?P<fleet_id>[-\w]+)/trips/finished/
        fleet = get_object_or_404(Fleet, id=fleet_id, owner=request.user.owner)
        trips = Trip.objects.filter(fleet=fleet, is_finished=True)
        serialized_trips = TripSerializer(trips, many=True)
        return Response(serialized_trips.data, status=status.HTTP_200_OK)


# DRIVER API
class DriverPendingFleets(APIView):
    permission_classes = (IsDriverPermission,)
    authentication_classes = (CsrfExemptSessionAuthentication, BasicAuthentication)

    def get(self, request):
        #GET /api/driver/pending_fleets/
        pending_fleets = request.user.driver.pending_fleets
        serialized_pending_fleets = FleetSerializer(pending_fleets, many=True)
        return Response(serialized_pending_fleets.data, status=status.HTTP_200_OK)


class DriverPendingFleetsAccept(APIView):
    permission_classes = (IsDriverPermission,)
    authentication_classes = (CsrfExemptSessionAuthentication, BasicAuthentication)

    def post(self, request):
        # POST /api/driver/pending_fleets/accept/
        form_pending_to_fleet = DriverPendingFleetAddDeclineForm(request.data)
        if form_pending_to_fleet.is_valid():
            try:
                fleets = request.user.driver.fleets
                pending_fleets = request.user.driver.pending_fleets
                ids = form_pending_to_fleet.cleaned_data.get('fleet_id')
                for fleet_id in ids.split(sep=','):
                    try:
                        waited_fleet = Fleet.objects.get(id=fleet_id)
                        print(waited_fleet.id)
                    except Exception as e:
                        return Response({"status": "error", "errors": [str(e)]}, status=status.HTTP_409_CONFLICT)
                    if waited_fleet is not None:
                        if waited_fleet in pending_fleets.all():
                            pending_fleets.remove(waited_fleet)
                            fleets.add(waited_fleet)
                    print("accepted " + str(waited_fleet.id) + " by " + str(request.user.username))
                return Response({"status": "ok"}, status=status.HTTP_200_OK)
            except Exception as e:
                return Response({"status": "error", "errors": [str(e)]}, status=status.HTTP_409_CONFLICT)
        else:
            return Response({"status": "error"}, status=status.HTTP_400_BAD_REQUEST)


class DriverPendingFleetsDecline(APIView):
    permission_classes = (IsDriverPermission,)
    authentication_classes = (CsrfExemptSessionAuthentication, BasicAuthentication)

    def post(self, request):
        # POST /api/driver/pending_fleets/decline/
        form_pending_decline = DriverPendingFleetAddDeclineForm(request.data)
        if form_pending_decline.is_valid():
            try:
                pending_fleets = request.user.driver.pending_fleets
                ids = form_pending_decline.cleaned_data.get('fleet_id')
                for fleet_id in ids.split(sep=','):
                    try:
                        waited_fleet = Fleet.objects.get(id=fleet_id)
                        print(waited_fleet.id)
                    except Exception as e:
                        return Response({"status": "error", "errors": [str(e)]}, status=status.HTTP_409_CONFLICT)
                    if waited_fleet is not None:
                        if waited_fleet in pending_fleets.all():
                            pending_fleets.remove(waited_fleet)
                    print("declined " + str(waited_fleet.id) + " by " + str(request.user.username))
                return Response({"status": "ok"}, status=status.HTTP_200_OK)
            except Exception as e:
                return Response({"status": "error", "errors": [str(e)]}, status=status.HTTP_409_CONFLICT)
        else:
            return Response({"status": "error"}, status=status.HTTP_400_BAD_REQUEST)


class DriverFleets(APIView):
    permission_classes = (IsDriverPermission,)
    authentication_classes = (CsrfExemptSessionAuthentication, BasicAuthentication)

    def get(self, request):
        #GET /api/driver/fleets/
        fleets = request.user.driver.fleets
        serialized_fleets = FleetSerializer(fleets, many=True)
        return Response(serialized_fleets.data, status=status.HTTP_200_OK)


class DriverFleetAvailableTrips(APIView):
    permission_classes = (IsDriverPermission,)
    authentication_classes = (CsrfExemptSessionAuthentication, BasicAuthentication)

    def get(self, request, fleet_id):
        #GET /api/driver/fleet/<fleet_id>/available_trips/
        try:
            fleet = Fleet.objects.get(id=fleet_id)
        except:
            return Response({"status": "error"}, status=status.HTTP_404_NOT_FOUND)
        trips = Trip.objects.none()
        if fleet in request.user.driver.fleets.all():
            trips = Trip.objects.filter(fleet=fleet, driver=None, is_finished=False)
        serialized_trips = TripSerializer(trips, many=True)
        return Response(serialized_trips.data, status=status.HTTP_200_OK)


class DriverAvailableTrips(APIView):
    permission_classes = (IsDriverPermission,)
    authentication_classes = (CsrfExemptSessionAuthentication, BasicAuthentication)

    def get(self, request):
        #GET /api/driver/available_trips/
        fleets = request.user.driver.fleets
        trips = Trip.objects.none()
        for fleet in fleets.all():
            trips_add = Trip.objects.filter(fleet=fleet, driver=None, is_finished=False)
            trips = trips | trips_add
        serialized_trips = TripSerializer(trips, many=True)
        return Response(serialized_trips.data, status=status.HTTP_200_OK)


class DriverFleetTrips(APIView):
    permission_classes = (IsDriverPermission,)
    authentication_classes = (CsrfExemptSessionAuthentication, BasicAuthentication)

    def get(self, request, fleet_id):
        #GET /api/driver/fleet/<fleet_id>/trips/
        try:
            fleet = Fleet.objects.get(id=fleet_id)
            print(fleet)
        except:
            return Response({"status": "error"}, status=status.HTTP_409_CONFLICT)
        trips = Trip.objects.none()
        if fleet in request.user.driver.fleets.all():
            trips = Trip.objects.filter(fleet=fleet, driver=request.user.driver)
        serialized_trips = TripSerializer(trips, many=True)
        return Response(serialized_trips.data, status=status.HTTP_200_OK)


class DriverTrips(APIView):
    permission_classes = (IsDriverPermission,)
    authentication_classes = (CsrfExemptSessionAuthentication, BasicAuthentication)

    def get(self, request):
        #GET /api/driver/trips/
        fleets = request.user.driver.fleets
        trips = Trip.objects.none()
        for fleet in fleets.all():
            trips_add = Trip.objects.filter(fleet=fleet, driver=request.user.driver)
            trips = trips | trips_add
        serialized_trips = TripSerializer(trips, many=True)
        return Response(serialized_trips.data, status=status.HTTP_200_OK)


class TripById(APIView):
    permission_classes = (IsOwnerOrDriverPermission,)
    authentication_classes = (CsrfExemptSessionAuthentication, BasicAuthentication)

    def get(self, request, trip_id):
        #GET /api/driver/trips/
        trip = get_object_or_404(Trip, id=trip_id)
        current_user = request.user
        if is_driver(current_user) and trip.driver!=current_user.driver:
            return Response({"status": "error", "errors": "Not your trip"},status=status.HTTP_409_CONFLICT)
        if is_owner(current_user) and (trip.fleet.owner!=current_user.owner):
            return Response({"status": "error", "errors": "Not your trip"}, status=status.HTTP_409_CONFLICT)
        serialized_trips = TripSerializer(trip)
        return Response(serialized_trips.data, status=status.HTTP_200_OK)


class DriverAcceptTrip(APIView):
    permission_classes = (IsDriverPermission,)
    authentication_classes = (CsrfExemptSessionAuthentication, BasicAuthentication)

    def post(self, request):
        #POST /api/driver/accept_trip/
        driver = request.user.driver
        trip_id_form = DriverAcceptTripForm(request.data)
        if not trip_id_form.is_valid():
            return Response({"status": "trip_id_form not valid"}, status=status.HTTP_400_BAD_REQUEST)
        trip_id = trip_id_form.cleaned_data.get('trip_id')
        trip = get_object_or_404(Trip, id=trip_id)
        try:
            print(trip, trip.id, trip.fleet, trip.driver, trip.is_finished)
            print(driver, driver.fleets.all())
            if trip.driver == driver and trip.is_finished:
                return Response({"status": "error", "errors": "You have already been finished this trip"},
                                status=status.HTTP_409_CONFLICT)
            elif trip.driver == driver:
                # TODO Redirect to page with current trip
                return Response({"status": "error", "errors": "It's your current trip"},
                                status=status.HTTP_409_CONFLICT)
            elif trip.driver is not None:
                return Response({"status": "error", "errors": "This trip has already been accepted"},
                                status=status.HTTP_409_CONFLICT)
            elif trip.is_finished:
                return Response({"status": "error", "errors": "This trip is finished but don't have a driver!!!"},
                                status=status.HTTP_409_CONFLICT)
            if trip.fleet not in driver.fleets.all():
                return Response({"status": "error", "errors": "You are not a member in that fleet"},
                                status=status.HTTP_409_CONFLICT)
            if Trip.objects.filter(driver=driver, is_finished=False).exists():
                # TODO Redirect to page with current trip
                return Response({"status": "error", "errors": "You have already accepted current trip"},
                                status=status.HTTP_409_CONFLICT)
            # TODO Change 1 to static variable
            if trip.problem is not 1:
                return Response({"status": "error", "errors": "The trip has a problem"},
                                status=status.HTTP_409_CONFLICT)
            trip.driver = driver
            trip.save()
            return Response({"status": "ok"}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"status": "error", "errors": [str(e)]}, status=status.HTTP_409_CONFLICT)


class AddTrip(APIView):
    permission_classes = (IsOwnerOrDriverPermission,)
    authentication_classes = (CsrfExemptSessionAuthentication, BasicAuthentication)

    def post(self, request, fleet_id):
        #POST /api/driver/fleet/<fleet_id>/add_trip/
        form_add_trip = AddTripForm(request.data)
        if form_add_trip.is_valid():
            try:
                fleet = get_object_or_404(Fleet, id=fleet_id)
                current_user = request.user
                if is_driver(current_user) and (not fleet in current_user.driver.fleets.all()):
                    return Response({"status": "error", "errors": "You are not a member in that fleet"}, status=status.HTTP_409_CONFLICT)
                if is_owner(current_user) and (fleet.owner != current_user.owner):
                    return Response({"status": "error", "errors": "It is not your fleet"}, status=status.HTTP_409_CONFLICT)

                trip = form_add_trip.save(commit=False)
                trip.start_date = timezone.now()
                trip.fleet = fleet
                trip.save()
                trip.name = str(fleet.name)+"#"+str(trip.id)
                trip.save()
                print(trip.name, trip.description, trip.driver, trip.fleet, trip.start_date, trip.id)
                return Response({"status": "ok"}, status=status.HTTP_201_CREATED)
            except Exception as e:
                return Response({"status": "error", "errors": [str(e)]}, status=status.HTTP_409_CONFLICT)
        else:
            return Response({"status": "error"}, status=status.HTTP_400_BAD_REQUEST)


class DriverCurrentTrip(APIView):
    permission_classes = (IsDriverPermission,)
    authentication_classes = (CsrfExemptSessionAuthentication, BasicAuthentication)

    def get(self, request):
        #GET GET /api/driver/current_trip/
        try:
            trip = Trip.objects.get(driver=request.user.driver, is_finished=False)
        except:
            return Response({"status": "error", "errors": "You have not current trip"},
                            status=status.HTTP_409_CONFLICT)
        print(trip, trip.id, trip.fleet)
        try:
            serialized_trip = TripSerializer(trip)
            return Response(serialized_trip.data, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"status": "error", "errors": [str(e)]}, status=status.HTTP_409_CONFLICT)


class DriverReportProblem(APIView):
    permission_classes = (IsDriverPermission,)
    authentication_classes = (CsrfExemptSessionAuthentication, BasicAuthentication)

    def post(self, request):
        #POST /api/driver/report_problem/
        try:
            trip = Trip.objects.get(driver=request.user.driver, is_finished=False)
        except:
            return Response({"status": "error", "errors": "You have not current trip"},
                            status=status.HTTP_409_CONFLICT)
        form_report_problem = DriverReportProblemForm(request.data, instance=trip)
        if form_report_problem.is_valid():
            try:
                print(trip.problem)
                form_report_problem.save()
                print(trip.problem)
                return Response({"status": "ok"}, status=status.HTTP_200_OK)
            except Exception as e:
                return Response({"status": "error", "errors": [str(e)]}, status=status.HTTP_409_CONFLICT)
        else:
            return Response({"status": "error"}, status=status.HTTP_400_BAD_REQUEST)


class DriverFinishTrip(APIView):
    permission_classes = (IsDriverPermission,)
    authentication_classes = (CsrfExemptSessionAuthentication, BasicAuthentication)

    def post(self, request):
        #POST /api/driver/finish_trip/
        try:
            trip = Trip.objects.get(driver=request.user.driver, is_finished=False)
        except:
            return Response({"status": "error", "errors": "You have no current trip"},
                            status=status.HTTP_409_CONFLICT)
        print(trip, trip.id, trip.fleet)
        try:
            trip.is_finished = True
            trip.end_date = timezone.now()
            trip.save()
            deleteDriverPos(trip.fleet, request.user.driver)
            return Response({"status": "ok"}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"status": "error", "errors": [str(e)]}, status=status.HTTP_409_CONFLICT)


class DriverUpdatePos(APIView):
    permission_classes = (IsDriverPermission,)
    authentication_classes = (CsrfExemptSessionAuthentication, BasicAuthentication)

    def post(self, request):
        #POST /api/driver/update_pos/
        driver = request.user.driver
        if filterSpam(driver.id):
            print("Filtered too frequent request by driver_id="+str(driver.id))
            return Response({"status": "error", "errors": "Too frequent requests"}, status=status.HTTP_409_CONFLICT)

        try:
            trip = Trip.objects.get(driver=driver, is_finished=False)
        except:
            return Response({"status": "error", "errors": "You have no current trip"},
                            status=status.HTTP_409_CONFLICT)

        update_pos_form = DriverUpdatePosForm(request.data)
        if not update_pos_form.is_valid():
            return Response({"status": "update_pos_form not valid"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            lat = update_pos_form.cleaned_data.get('lat')
            lon = update_pos_form.cleaned_data.get('lon')
            updateDriverPos(trip.fleet, driver, lat, lon)
            return Response({"status": "ok"}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"status": "error", "errors": [str(e)]}, status=status.HTTP_409_CONFLICT)


class ReloadGeo(APIView):
    # TODO admin only
    # permission_classes = (IsOwnerOrDriverPermission,)
    authentication_classes = (CsrfExemptSessionAuthentication, BasicAuthentication)

    def get(self, request):
        # GET /api/reload/
        try:
            clearAllFleetChannels()
            return Response({"status": "ok"}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"status": "error", "errors": [str(e)]}, status=status.HTTP_409_CONFLICT)


spam_driver_dict = {}
time_interval = 5 # 5 секунд
def filterSpam(driver_id):
    time_now = timezone.now()
    last_activity = spam_driver_dict.get(driver_id, None)
    if(last_activity is None or (time_now-last_activity).seconds >= time_interval):
        spam_driver_dict[driver_id] = time_now
        return False
    return True